// Application-side, temporary WFP containment for Valve's unauthenticated
// VConsole listener. Never loaded into CS2; no persistent firewall rules.
#include <winsock2.h>
#include <windows.h>
#include <fwpmu.h>
#include <rpc.h>
#include <filesystem>
#include <fstream>
#include <string>

namespace fs = std::filesystem;

struct Engine {
    HANDLE handle = nullptr;
    ~Engine() { if (handle) FwpmEngineClose0(handle); }
};

int wmain(int argc, wchar_t** argv) {
    if (argc != 5) return 2;
    DWORD parent = wcstoul(argv[1], nullptr, 10);
    unsigned long port = wcstoul(argv[2], nullptr, 10);
    fs::path exe = fs::absolute(argv[3]), folder = fs::absolute(argv[4]);
    if (!parent || port < 49152 || port > 65535 ||
        _wcsicmp(exe.filename().c_str(), L"cs2.exe") || !fs::is_regular_file(exe) ||
        !fs::is_directory(folder)) return 2;
    HANDLE owner = OpenProcess(SYNCHRONIZE, FALSE, parent);
    if (!owner) return 3;
    Engine engine;
    FWPM_SESSION0 session{};
    session.flags = FWPM_SESSION_FLAG_DYNAMIC;
    session.displayData.name = const_cast<wchar_t*>(L"CS2 Toolbox private demo controls");
    DWORD error = FwpmEngineOpen0(nullptr, RPC_C_AUTHN_WINNT, nullptr, &session, &engine.handle);
    UINT64 ids[2]{};
    FWP_BYTE_BLOB* app = nullptr;
    if (!error) error = FwpmGetAppIdFromFileName0(exe.c_str(), &app);
    if (!error) error = FwpmTransactionBegin0(engine.handle, 0);
    if (!error) {
        FWPM_FILTER_CONDITION0 conditions[4]{};
        conditions[0].fieldKey = FWPM_CONDITION_ALE_APP_ID;
        conditions[0].conditionValue.type = FWP_BYTE_BLOB_TYPE;
        conditions[0].conditionValue.byteBlob = app;
        conditions[1].fieldKey = FWPM_CONDITION_IP_PROTOCOL;
        conditions[1].conditionValue.type = FWP_UINT8;
        conditions[1].conditionValue.uint8 = IPPROTO_TCP;
        conditions[2].fieldKey = FWPM_CONDITION_IP_LOCAL_PORT;
        conditions[2].conditionValue.type = FWP_UINT16;
        conditions[2].conditionValue.uint16 = static_cast<UINT16>(port);
        conditions[3].fieldKey = FWPM_CONDITION_FLAGS;
        conditions[3].matchType = FWP_MATCH_FLAGS_NONE_SET;
        conditions[3].conditionValue.type = FWP_UINT32;
        conditions[3].conditionValue.uint32 = FWP_CONDITION_FLAG_IS_LOOPBACK;
        const GUID layers[] = {FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4, FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6};
        for (int i=0; i<2 && !error; ++i) {
            FWPM_FILTER0 filter{};
            UuidCreate(&filter.filterKey);
            filter.displayData.name = session.displayData.name;
            filter.layerKey = layers[i];
            filter.subLayerKey = FWPM_SUBLAYER_UNIVERSAL;
            filter.weight.type = FWP_UINT8; filter.weight.uint8 = 15;
            filter.numFilterConditions = 4; filter.filterCondition = conditions;
            filter.action.type = FWP_ACTION_BLOCK;
            error = FwpmFilterAdd0(engine.handle, &filter, nullptr, &ids[i]);
        }
        if (!error) error = FwpmTransactionCommit0(engine.handle);
        else FwpmTransactionAbort0(engine.handle);
    }
    if (app) FwpmFreeMemory0(reinterpret_cast<void**>(&app));
    {
        std::ofstream out(folder / L"guard-result.tmp");
        out << "{\"ok\":" << (error ? "false" : "true") << ",\"error\":" << error
            << ",\"port\":" << port << ",\"filters\":[" << ids[0] << "," << ids[1] << "]}";
        out.close(); fs::rename(folder / L"guard-result.tmp", folder / L"guard-result.json");
    }
    if (!error) {
        while (WaitForSingleObject(owner, 250) == WAIT_TIMEOUT && !fs::exists(folder / L"stop")) {}
    }
    CloseHandle(owner);
    return error ? 1 : 0;
}
