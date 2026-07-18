#include "stdafx.h"
#include "bugfix_mod_checks.hpp"
#include "common.hpp"
#include "config.hpp"
#include "logging.hpp"
#include "submodule_initiailization.hpp"
#include "version_checking.hpp"
#include "cleanup_loose_outdated_files.hpp"

static bool DetectGame()
{
    eGameType = UNKNOWN;
    // Special handling for launcher.exe
    if (sExeName == "launcher.exe")
    {
        for (const auto& [type, info] : kGames)
        {
            auto gamePath = sExePath.parent_path() / info.ExeName;
            if (std::filesystem::exists(gamePath))
            {
                spdlog::info("Detected launcher for game: {} (app {})", info.GameTitle.c_str(), info.SteamAppId);
                eGameType = LAUNCHER;
                unityPlayer = GetModuleHandleA("UnityPlayer.dll");
                game = &info;
                return true;
            }
        }

        spdlog::error("Failed to detect supported game, unknown launcher");
        FreeLibraryAndExitThread(baseModule, 1);
    }

    for (const auto& [type, info] : kGames)
    {
        if (info.ExeName == sExeName)
        {
            spdlog::info("Detected game: {} (app {})", info.GameTitle.c_str(), info.SteamAppId);
            eGameType = type;
            game = &info;

            sGameSavePath = sExePath / (eGameType & MG ? "mg12_savedata_win" : eGameType & MGS2 ? "mgs2_savedata_win" : "mgs3_savedata_win");
            spdlog::info("Game Save Path: {}", sGameSavePath.string());
            if (engineModule = GetModuleHandleA("Engine.dll"); !engineModule)
            {
                spdlog::error("Failed to get Engine.dll module handle");
            }
            return true;
        }
    }

    spdlog::error("Failed to detect supported game, {} isn't supported by MGS2-Community-Bugfix-Compilation", sExeName.c_str());
    FreeLibraryAndExitThread(baseModule, 1);
}



static void InitializeSubsystems()
{
    //Initialization order (these systems initialize vars used by following ones.)
    INITIALIZE(g_Logging.LogSysInfo());            //0
    INITIALIZE(DetectGame());                      //1
    INITIALIZE(Config::Read());

    if (!(eGameType & LAUNCHER))
    {
        INITIALIZE(VerifyInstallation::Check());
        INITIALIZE(CleanupOutdatedModfiles::Check());
        INITIALIZE(CheckForUpdates());
    }

    INITIALIZE(Util::ShutdownSHA1Provider());

}

DWORD __stdcall Main(void*)
{
    g_Logging.initStartTime = std::chrono::high_resolution_clock::now();
    g_Logging.Initialize();

    INITIALIZE(InitializeSubsystems());

    spdlog::info("All systems initialized. shutting down {}.", sFixName);
    spdlog::shutdown();
    FreeLibraryAndExitThread(baseModule, 0);

    return TRUE;
}



BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    if (ul_reason_for_call == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(hModule);

        if (const HANDLE mainHandle = CreateThread(nullptr, 0, Main, nullptr, 0, nullptr))
        {
            CloseHandle(mainHandle);
        }
    }

    return TRUE;
}
