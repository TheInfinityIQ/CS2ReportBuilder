// Optional visual-reference recorder. Windows Media Foundation only; no game
// hooks or game-file writes. The normal GPU display path remains unchanged.
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <cmath>
#include <array>
#include <vector>

struct ReferenceVideo {
    winrt::com_ptr<IMFSinkWriter> writer;
    winrt::com_ptr<ID3D11Texture2D> staging;
    std::array<uint8_t,65536> srgb{};
    DWORD stream{};
    int width{},height{},fps{30};
    uint64_t frames{};
    LARGE_INTEGER start{},frequency{};
    HRESULT failure{S_OK};
    bool started{};
    std::vector<uint8_t> latest;

    ReferenceVideo(const wchar_t* path,int w,int h,ID3D11Device* device):width(w),height(h) {
        if(w<2 || h<2 || w%2 || h%2 || w>7680 || h>4320)throw winrt::hresult_invalid_argument();
        winrt::check_hresult(MFStartup(MF_VERSION));started=true;
        try {
            for(unsigned bits=0;bits<65536;bits++) {
                unsigned exponent=(bits>>10)&31,mantissa=bits&1023;
                float value=exponent?std::ldexp(1.0f+mantissa/1024.0f,int(exponent)-15):std::ldexp(float(mantissa),-24);
                if(bits&32768)value=0;
                if(exponent==31)value=mantissa?0:1;
                value=std::clamp(value,0.0f,1.0f);
                value=value<=.0031308f?12.92f*value:1.055f*std::pow(value,1.0f/2.4f)-.055f;
                srgb[bits]=uint8_t(std::clamp(value*255.0f+.5f,0.0f,255.0f));
            }
            winrt::check_hresult(MFCreateSinkWriterFromURL(path,nullptr,nullptr,writer.put()));
            winrt::com_ptr<IMFMediaType> output,input;
            winrt::check_hresult(MFCreateMediaType(output.put()));
            winrt::check_hresult(output->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));
            winrt::check_hresult(output->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_H264));
            winrt::check_hresult(output->SetUINT32(MF_MT_AVG_BITRATE,16000000));
            winrt::check_hresult(output->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive));
            winrt::check_hresult(MFSetAttributeSize(output.get(),MF_MT_FRAME_SIZE,w,h));
            winrt::check_hresult(MFSetAttributeRatio(output.get(),MF_MT_FRAME_RATE,fps,1));
            winrt::check_hresult(MFSetAttributeRatio(output.get(),MF_MT_PIXEL_ASPECT_RATIO,1,1));
            winrt::check_hresult(writer->AddStream(output.get(),&stream));
            winrt::check_hresult(MFCreateMediaType(input.put()));
            winrt::check_hresult(input->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));
            winrt::check_hresult(input->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32));
            winrt::check_hresult(input->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive));
            winrt::check_hresult(input->SetUINT32(MF_MT_DEFAULT_STRIDE,w*4));
            winrt::check_hresult(MFSetAttributeSize(input.get(),MF_MT_FRAME_SIZE,w,h));
            winrt::check_hresult(MFSetAttributeRatio(input.get(),MF_MT_FRAME_RATE,fps,1));
            winrt::check_hresult(MFSetAttributeRatio(input.get(),MF_MT_PIXEL_ASPECT_RATIO,1,1));
            winrt::check_hresult(writer->SetInputMediaType(stream,input.get(),nullptr));
            winrt::check_hresult(writer->BeginWriting());
            D3D11_TEXTURE2D_DESC desc{};
            desc.Width=w;desc.Height=h;desc.MipLevels=desc.ArraySize=desc.SampleDesc.Count=1;
            desc.Format=DXGI_FORMAT_R16G16B16A16_FLOAT;desc.Usage=D3D11_USAGE_STAGING;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
            winrt::check_hresult(device->CreateTexture2D(&desc,nullptr,staging.put()));
            QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&start);
        } catch(...) {writer=nullptr;MFShutdown();started=false;throw;}
    }

    void append(ID3D11DeviceContext* context,ID3D11Texture2D* texture) {
        if(FAILED(failure))return;
        LARGE_INTEGER now{};QueryPerformanceCounter(&now);
        LONGLONG timestamp=LONGLONG((now.QuadPart-start.QuadPart)*10000000LL/frequency.QuadPart);
        if(timestamp<LONGLONG(frames)*10000000/fps)return;
        D3D11_BOX box{0,0,0,UINT(width),UINT(height),1};
        context->CopySubresourceRegion(staging.get(),0,0,0,0,texture,0,&box);
        D3D11_MAPPED_SUBRESOURCE mapped{};
        winrt::check_hresult(context->Map(staging.get(),0,D3D11_MAP_READ,0,&mapped));
        winrt::com_ptr<IMFMediaBuffer> buffer;
        HRESULT status=MFCreateMemoryBuffer(width*height*4,buffer.put());
        if(FAILED(status)){context->Unmap(staging.get(),0);winrt::check_hresult(status);}
        BYTE* bytes{};status=buffer->Lock(&bytes,nullptr,nullptr);
        if(FAILED(status)){context->Unmap(staging.get(),0);winrt::check_hresult(status);}
        for(int y=0;y<height;y++) {
            auto row=reinterpret_cast<const uint16_t*>(static_cast<const BYTE*>(mapped.pData)+y*mapped.RowPitch);
            auto dest=bytes+(height-1-y)*width*4; // RGB32 input uses bottom-up rows.
            for(int x=0;x<width;x++){dest[x*4]=srgb[row[x*4+2]];dest[x*4+1]=srgb[row[x*4+1]];dest[x*4+2]=srgb[row[x*4]];dest[x*4+3]=255;}
        }
        latest.assign(bytes,bytes+width*height*4);
        buffer->Unlock();context->Unmap(staging.get(),0);
        winrt::check_hresult(buffer->SetCurrentLength(width*height*4));
        winrt::com_ptr<IMFSample> sample;winrt::check_hresult(MFCreateSample(sample.put()));
        winrt::check_hresult(sample->AddBuffer(buffer.get()));
        winrt::check_hresult(sample->SetSampleTime(timestamp));
        winrt::check_hresult(sample->SetSampleDuration(10000000/fps));
        winrt::check_hresult(writer->WriteSample(stream,sample.get()));frames++;
    }

    HRESULT finish() noexcept {HRESULT result=writer?writer->Finalize():E_FAIL;writer=nullptr;return FAILED(failure)?failure:result;}
    ~ReferenceVideo(){if(writer)writer->Finalize();if(started)MFShutdown();}
};
