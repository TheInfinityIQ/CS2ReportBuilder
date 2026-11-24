// All code runs in Toolbox's process. No hooks, input, or writes to the source.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <roapi.h>
#include <d3d11.h>
#include <dxgi1_6.h>
#include <dcomp.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <algorithm>
#include <cstring>
#include <atomic>
#include <memory>
#include <mutex>
#include <string>

using namespace winrt;
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;
using ::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess;

#include "video_writer.h"

namespace {
constexpr auto format = DirectXPixelFormat::R16G16B16A16Float;
constexpr auto dxgiFormat = DXGI_FORMAT_R16G16B16A16_FLOAT;
struct Stats {
    uint64_t frames;
    int32_t width, height, state, error;
    double secondsSinceFrame;
};

struct Capture : std::enable_shared_from_this<Capture> {
    HWND source{}, destination{};
    std::mutex mutex;
    std::atomic<bool> stopped{false};
    GraphicsCaptureItem item{nullptr};
    Direct3D11CaptureFramePool pool{nullptr};
    GraphicsCaptureSession session{nullptr};
    event_token frameToken{};
    bool subscribed{};
    IDirect3DDevice winDevice{nullptr};
    com_ptr<ID3D11Device> device;
    com_ptr<ID3D11DeviceContext> context;
    com_ptr<IDXGIFactory2> factory;
    com_ptr<IDXGISwapChain1> swap;
    com_ptr<IDCompositionDevice> composition;
    com_ptr<IDCompositionTarget> target;
    com_ptr<IDCompositionVisual> visual;
    int width{}, height{};
    uint64_t frames{};
    LARGE_INTEGER last{}, frequency{};
    HRESULT failure{S_OK};
    std::unique_ptr<ReferenceVideo> recording;

    void arrange() {
        if (!swap || !width || !height) return;
        RECT rect{};
        check_bool(GetClientRect(destination, &rect));
        float w = float(rect.right), h = float(rect.bottom);
        if (w <= 0 || h <= 0) return;
        float scale = std::min(w / width, h / height);
        D2D_MATRIX_3X2_F transform{scale, 0, 0, scale,
            (w - width * scale) / 2, (h - height * scale) / 2};
        check_hresult(visual->SetTransform(transform));
        check_hresult(composition->Commit());
    }

    void createSwap(int w, int h) {
        if (swap && width == w && height == h) return;
        if (swap) {
            check_hresult(swap->ResizeBuffers(2, w, h, dxgiFormat, 0));
        } else {
            DXGI_SWAP_CHAIN_DESC1 desc{};
            desc.Width = w; desc.Height = h; desc.Format = dxgiFormat;
            desc.SampleDesc.Count = 1;
            desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
            desc.BufferCount = 2;
            desc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
            desc.Scaling = DXGI_SCALING_STRETCH;
            desc.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;
            check_hresult(factory->CreateSwapChainForComposition(device.get(), &desc, nullptr, swap.put()));
            auto color = swap.as<IDXGISwapChain3>();
            // scRGB throughout; do not change OS or game HDR settings.
            check_hresult(color->SetColorSpace1(DXGI_COLOR_SPACE_RGB_FULL_G10_NONE_P709));
            check_hresult(visual->SetContent(swap.get()));
        }
        width = w; height = h;
        arrange();
    }

    void start(HWND src, HWND dst) {
        // Tk exposes its client HWND; WGC needs the top-level wrapper window.
        src = GetAncestor(src, GA_ROOT);
        source = src; destination = dst;
        if (!IsWindow(src) || !IsWindow(dst) || src == dst) throw hresult_invalid_argument();
        DWORD pid{}; GetWindowThreadProcessId(dst, &pid);
        if (pid != GetCurrentProcessId()) throw hresult_access_denied();
        if (!GraphicsCaptureSession::IsSupported()) throw hresult_not_implemented();
        QueryPerformanceFrequency(&frequency);
        check_hresult(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
            device.put(), nullptr, context.put()));
        auto dxgi = device.as<IDXGIDevice>();
        com_ptr<IDXGIAdapter> adapter;
        check_hresult(dxgi->GetAdapter(adapter.put()));
        check_hresult(adapter->GetParent(__uuidof(IDXGIFactory2), factory.put_void()));
        check_hresult(DCompositionCreateDevice(dxgi.get(), __uuidof(IDCompositionDevice), composition.put_void()));
        check_hresult(composition->CreateTargetForHwnd(dst, TRUE, target.put()));
        check_hresult(composition->CreateVisual(visual.put()));
        check_hresult(target->SetRoot(visual.get()));
        com_ptr<IInspectable> inspectable;
        check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.get(), inspectable.put()));
        winDevice = inspectable.as<IDirect3DDevice>();
        auto interop = get_activation_factory<GraphicsCaptureItem, IGraphicsCaptureItemInterop>();
        check_hresult(interop->CreateForWindow(src, guid_of<GraphicsCaptureItem>(), put_abi(item)));
        auto size = item.Size();
        if (size.Width <= 0 || size.Height <= 0) throw hresult_invalid_argument();
        createSwap(size.Width, size.Height);
        pool = Direct3D11CaptureFramePool::CreateFreeThreaded(winDevice, format, 2, size);
        session = pool.CreateCaptureSession(item);
        auto weak = weak_from_this();
        frameToken = pool.FrameArrived([weak](auto const& sender, auto const&) noexcept {
            if (auto self = weak.lock()) self->frame(sender);
        });
        subscribed = true;
        session.StartCapture();
    }

    void frame(Direct3D11CaptureFramePool const& sender) noexcept {
        if (stopped) return;
        try {
            std::lock_guard lock(mutex);
            if (stopped || FAILED(failure)) return;
            auto frame = sender.TryGetNextFrame();
            if (!frame) return;
            auto size = frame.ContentSize();
            if (size.Width <= 0 || size.Height <= 0) return;
            auto access = frame.Surface().as<IDirect3DDxgiInterfaceAccess>();
            com_ptr<ID3D11Texture2D> texture;
            check_hresult(access->GetInterface(__uuidof(ID3D11Texture2D), texture.put_void()));
            D3D11_TEXTURE2D_DESC desc{}; texture->GetDesc(&desc);
            bool resize = size.Width != width || size.Height != height;
            if (!resize && int(desc.Width) >= width && int(desc.Height) >= height) {
                com_ptr<ID3D11Texture2D> buffer;
                check_hresult(swap->GetBuffer(0, __uuidof(ID3D11Texture2D), buffer.put_void()));
                D3D11_BOX box{0, 0, 0, UINT(width), UINT(height), 1};
                context->CopySubresourceRegion(buffer.get(), 0, 0, 0, 0, texture.get(), 0, &box);
                if(recording) {
                    try {recording->append(context.get(),texture.get());}
                    catch(hresult_error const& e){recording->failure=e.code();}
                    catch(...){recording->failure=E_FAIL;}
                }
                check_hresult(swap->Present(1, 0));
                ++frames; QueryPerformanceCounter(&last);
            }
            texture = nullptr; frame.Close();
            if (resize) {
                createSwap(size.Width, size.Height);
                sender.Recreate(winDevice, format, 2, size);
            }
        } catch (hresult_error const& e) {
            if (!stopped) { std::lock_guard lock(mutex); failure = e.code(); }
        } catch (...) {
            if (!stopped) { std::lock_guard lock(mutex); failure = E_FAIL; }
        }
    }

    void stop() noexcept {
        if (stopped.exchange(true)) return;
        // Closing outside the callback mutex avoids waiting on a locked callback.
        try { if (subscribed) pool.FrameArrived(frameToken); } catch (...) {}
        try { if (session) session.Close(); } catch (...) {}
        try { if (pool) pool.Close(); } catch (...) {}
        std::lock_guard lock(mutex);
        recording.reset();
        try { if (visual) visual->SetContent(nullptr); if (composition) composition->Commit(); } catch (...) {}
    }
    ~Capture() { stop(); }
};
using Handle = std::shared_ptr<Capture>;
struct Apartment {
    HRESULT result{RoInitialize(RO_INIT_SINGLETHREADED)};
    ~Apartment() { if (SUCCEEDED(result)) RoUninitialize(); }
};
void error(wchar_t* buffer, int length, wchar_t const* value) noexcept {
    if (buffer && length > 0) wcsncpy_s(buffer, length, value, _TRUNCATE);
}
}

extern "C" __declspec(dllexport) void* __cdecl nv_create(HWND source, HWND destination, wchar_t* message, int length) noexcept {
    try {
        // Matches Tk's UI thread; WinRT initialization does not change process DPI.
        thread_local Apartment apartment;
        if (FAILED(apartment.result) && apartment.result != RPC_E_CHANGED_MODE) check_hresult(apartment.result);
        auto capture = std::make_shared<Capture>();
        capture->start(source, destination);
        return new Handle(std::move(capture));
    } catch (hresult_error const& e) {
        wchar_t code[32]{}; swprintf_s(code, L" (0x%08X)", unsigned(e.code().value));
        auto detail = std::wstring(e.message()) + code;
        error(message, length, detail.c_str());
    }
      catch (...) { error(message, length, L"Native capture could not start."); }
    return nullptr;
}

extern "C" __declspec(dllexport) int __cdecl nv_resize(void* raw) noexcept {
    try {
        auto& capture = *static_cast<Handle*>(raw);
        std::lock_guard lock(capture->mutex);
        if (!capture->stopped) capture->arrange();
        return 1;
    } catch (...) { return 0; }
}

extern "C" __declspec(dllexport) int __cdecl nv_stats(void* raw, Stats* out) noexcept {
    if (!raw || !out) return 0;
    auto& c = *static_cast<Handle*>(raw);
    std::lock_guard lock(c->mutex);
    LARGE_INTEGER now{}; QueryPerformanceCounter(&now);
    out->frames = c->frames; out->width = c->width; out->height = c->height;
    out->error = c->failure;
    out->state = FAILED(c->failure) ? 4 : !IsWindow(c->source) ? 3 : IsIconic(c->source) ? 2 : 1;
    out->secondsSinceFrame = c->last.QuadPart ? double(now.QuadPart - c->last.QuadPart) / c->frequency.QuadPart : -1;
    return 1;
}

// Diagnostic only: read one GPU pixel for bounded fixture tests, never per-frame UI.
extern "C" __declspec(dllexport) int __cdecl nv_sample(void* raw, int x, int y, uint16_t* rgba) noexcept {
    if (!raw || !rgba) return 0;
    try {
        auto& c = *static_cast<Handle*>(raw);
        std::lock_guard lock(c->mutex);
        if (!c->swap || !c->frames || x < 0 || y < 0 || x >= c->width || y >= c->height) return 0;
        com_ptr<ID3D11Texture2D> buffer, staging;
        check_hresult(c->swap->GetBuffer(0, __uuidof(ID3D11Texture2D), buffer.put_void()));
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width = desc.Height = desc.MipLevels = desc.ArraySize = desc.SampleDesc.Count = 1;
        desc.Format = dxgiFormat; desc.Usage = D3D11_USAGE_STAGING; desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        check_hresult(c->device->CreateTexture2D(&desc, nullptr, staging.put()));
        D3D11_BOX box{UINT(x), UINT(y), 0, UINT(x+1), UINT(y+1), 1};
        c->context->CopySubresourceRegion(staging.get(), 0, 0, 0, 0, buffer.get(), 0, &box);
        D3D11_MAPPED_SUBRESOURCE mapped{};
        check_hresult(c->context->Map(staging.get(), 0, D3D11_MAP_READ, 0, &mapped));
        std::memcpy(rgba, mapped.pData, 8); c->context->Unmap(staging.get(), 0);
        return 1;
    } catch (...) { return 0; }
}

extern "C" __declspec(dllexport) void __cdecl nv_stop(void* raw) noexcept {
    if (!raw) return;
    auto handle = static_cast<Handle*>(raw);
    (*handle)->stop();
    delete handle;
}

extern "C" __declspec(dllexport) int __cdecl nv_record_start(void* raw,const wchar_t* path) noexcept {
    if(!raw || !path)return 0;
    try {auto& c=*static_cast<Handle*>(raw);std::lock_guard lock(c->mutex);
        if(c->recording || !c->frames)return 0;
        c->recording=std::make_unique<ReferenceVideo>(path,c->width,c->height,c->device.get());return 1;
    }catch(hresult_error const& e){return int(e.code());}catch(...){return 0;}
}
extern "C" __declspec(dllexport) int64_t __cdecl nv_record_frames(void* raw) noexcept {
    if(!raw)return -1;auto& c=*static_cast<Handle*>(raw);std::lock_guard lock(c->mutex);
    return c->recording?(FAILED(c->recording->failure)?int64_t(c->recording->failure):int64_t(c->recording->frames)):-1;
}
extern "C" __declspec(dllexport) int __cdecl nv_record_end(void* raw) noexcept {
    if(!raw)return 0;auto& c=*static_cast<Handle*>(raw);std::lock_guard lock(c->mutex);
    if(!c->recording)return 0;HRESULT status=c->recording->finish();c->recording.reset();return SUCCEEDED(status)?1:int(status);
}
extern "C" __declspec(dllexport) int __cdecl nv_record_pixels(void* raw,uint8_t* pixels,uint32_t bytes) noexcept {
    if(!raw || !pixels)return 0;auto& c=*static_cast<Handle*>(raw);std::lock_guard lock(c->mutex);
    if(!c->recording || c->recording->latest.size()!=bytes)return 0;
    std::memcpy(pixels,c->recording->latest.data(),bytes);return 1;
}

// Offline verification of the actual encoded MP4, not merely its source frame.
extern "C" __declspec(dllexport) int __cdecl nv_video_frame(const wchar_t* path,int64_t time,
        uint8_t* pixels,uint32_t capacity,int* width,int* height,int64_t* duration,int* stride) noexcept {
    if(!path || !width || !height || !duration || !stride)return 0;
    struct MediaScope{HRESULT status{MFStartup(MF_VERSION)};~MediaScope(){if(SUCCEEDED(status))MFShutdown();}} media;
    try {
        Apartment apartment;check_hresult(media.status);
        com_ptr<IMFAttributes> attrs;check_hresult(MFCreateAttributes(attrs.put(),1));
        check_hresult(attrs->SetUINT32(MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING,TRUE));
        com_ptr<IMFSourceReader> reader;check_hresult(MFCreateSourceReaderFromURL(path,attrs.get(),reader.put()));
        com_ptr<IMFMediaType> requested;check_hresult(MFCreateMediaType(requested.put()));
        check_hresult(requested->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));
        check_hresult(requested->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32));
        check_hresult(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,requested.get()));
        com_ptr<IMFMediaType> type;check_hresult(reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,type.put()));
        UINT32 w{},h{};check_hresult(MFGetAttributeSize(type.get(),MF_MT_FRAME_SIZE,&w,&h));
        if(w>7680 || h>4320)throw hresult_invalid_argument();*width=int(w);*height=int(h);
        UINT32 pitch{};if(FAILED(type->GetUINT32(MF_MT_DEFAULT_STRIDE,&pitch)))pitch=w*4;*stride=int(pitch);
        PROPVARIANT length{};check_hresult(reader->GetPresentationAttribute(MF_SOURCE_READER_MEDIASOURCE,MF_PD_DURATION,&length));
        *duration=length.uhVal.QuadPart;PropVariantClear(&length);
        if(!pixels)return 1;
        if(capacity<uint64_t(std::abs(*stride))*h)throw hresult_invalid_argument();
        PROPVARIANT position{};position.vt=VT_I8;position.hVal.QuadPart=time;
        check_hresult(reader->SetCurrentPosition(GUID_NULL,position));
        com_ptr<IMFSample> sample;DWORD flags{};LONGLONG timestamp{};
        for(int attempt=0;attempt<120;attempt++) {
            check_hresult(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,nullptr,&flags,&timestamp,sample.put()));
            if(sample)break;
            if(flags&MF_SOURCE_READERF_ENDOFSTREAM)throw hresult_error(MF_E_END_OF_STREAM);
        }
        if(!sample)throw hresult_error(E_FAIL);
        com_ptr<IMFMediaBuffer> buffer;check_hresult(sample->ConvertToContiguousBuffer(buffer.put()));
        if(auto planar=buffer.try_as<IMF2DBuffer>()) {
            BYTE* top{};LONG pitch{};check_hresult(planar->Lock2D(&top,&pitch));
            for(UINT32 y=0;y<h;y++)std::memcpy(pixels+y*w*4,top+int64_t(y)*pitch,w*4);
            planar->Unlock2D();*stride=-int(w*4);return 1;
        }
        BYTE* data{};DWORD bytes{};check_hresult(buffer->Lock(&data,nullptr,&bytes));
        auto required=uint64_t(std::abs(*stride))*h;
        if(bytes<required){buffer->Unlock();throw hresult_invalid_argument();}
        std::memcpy(pixels,data,size_t(required));buffer->Unlock();return 1;
    }catch(hresult_error const& e){return int(e.code());}catch(...){return 0;}
}
