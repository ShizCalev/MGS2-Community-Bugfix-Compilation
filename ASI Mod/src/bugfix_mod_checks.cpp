// ReSharper disable CppUseAuto
// ReSharper disable IdentifierTypo
#include "stdafx.h"
#include "bugfix_mod_checks.hpp"

#include "common.hpp"
#include "logging.hpp"
#include "version.h"


//Community Bugfix hashes
constexpr const char* CBFC_BASE_FLATLIST_WIN_COL_ORANGE2_CTXR_SHA1 = "11d03110d40b42adeafde2fa5f5cf65f27d6fc52";
constexpr const char* CBFC_2x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1 = "e3b5923c9ce88a173a49d26e3bb4de2b77303b50";
constexpr const char* CBFC_4x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1 = "33003443c78e1162ef71d4a4521f1c02ceb54f6c";


constexpr const char* CBFC_2x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1 = "16d11c6f3800c098e4c7a643dc8b837136cce7be";
constexpr const char* CBFC_4x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1 = "a545a73f98a0e74ad58f6b56ddf87fea8a814635";



//Third party mod file hashes
constexpr const char* LIQMIX_SLOP_4X_ORANGE2_CTXR_SHA1 = "4ecda248b079ee426262a23b64df6cb05a249088";
constexpr const char* LIQMIX_SLOP_2X_ORANGE2_CTXR_SHA1 = "96ba1191c0da112d355bf510dcb3828f1183d1b5";

constexpr const char* HIGHER_RES_KOJIPRO_ZOE_POSTER_CTXR_SHA1 = "ce3fe5bd55aebb046103b5dba1cffa736b08abd2";


constexpr const char* GUYONACHAIR_HAIRFIX_SNA_HAIR3_V2_CTXR_SHA1 = "606cbad8a8b3e850b9a8b76f944bc3be25ed5f69";
constexpr const char* GUYONACHAIR_HAIRFIX_SNA_HAIR3_V1_CTXR_SHA1 = "f8ae30ee716bd43ed7af1e5b8d78a93d32711668";

constexpr const char* BETTER_AUDIO_p010_01_p01g_VAMP_SEAL_SDT_SHA1 = "3424163081275d9152b162d648b82616d3100ab1";

//Vanilla game hashes
constexpr const char* VANILLA_p010_01_p01g_VAMP_SEAL_SDT_SHA1 = "301dcbda56107c7d5617a98256369abbb2b94fee";

// todo - do all this shit in futures
// detect outdated ui files
// detect guy on a chair's old hair
// 

void VerifyInstallation::Check()
{
    struct FileHashResult
    {
        std::filesystem::path path;
        bool exists = false;
        std::optional<std::array<std::uint8_t, 20>> sha1;
    };



    const auto openCommunityBugfixPage =
        []()
        {
            ShellExecuteA(
                nullptr,
                "open",
                "https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files",
                nullptr,
                nullptr,
                SW_SHOWNORMAL
            );
        };


    auto startHashTask =
        [](const std::filesystem::path& path) -> std::future<FileHashResult>
        {
            return std::async(
                std::launch::async,
                [path]() -> FileHashResult
                {
                    FileHashResult result;
                    result.path = path;
                    result.exists = std::filesystem::exists(path);

                    if (!result.exists)
                    {
                        return result;
                    }

                    result.sha1 = Util::ComputeSHA1Bytes(path);
                    return result;
                });
        };

    const std::filesystem::path baseColOrange2Path = sExePath / "textures" / "flatlist" / "_win" / "col_orange2.bmp.ctxr";
    const std::filesystem::path ovrStmColOrange2Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "col_orange2.bmp.ctxr";
    const std::filesystem::path seculityCardPath = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "seculitycard_lv2_alp.bmp.ctxr";
    const std::filesystem::path betterAudioCheckPath = sExePath / "us" / "demo" / "_bp" / "p010_01_p01g.sdt";
    const std::filesystem::path zoePosterPath = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "zoe_pos_n.bmp.ctxr";
    const std::filesystem::path snakeHairPath = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair3.bmp.ctxr";

    const auto hashEquals =
        [](const FileHashResult& result, const char* expected) -> bool
        {
            return result.exists && result.sha1.has_value() && Util::SHA1Equals(*result.sha1, expected);
        };

    auto baseColOrange2Future = startHashTask(baseColOrange2Path);
    auto ovrStmColOrange2Future = startHashTask(ovrStmColOrange2Path);
    auto seculityCardFuture = startHashTask(seculityCardPath);
    auto betterAudioFuture = startHashTask(betterAudioCheckPath);
    auto zoePosterFuture = startHashTask(zoePosterPath);
    auto snakeHairFuture = startHashTask(snakeHairPath);

    const FileHashResult baseColOrange2Result = baseColOrange2Future.get();
    const FileHashResult ovrStmColOrange2Result = ovrStmColOrange2Future.get();
    const FileHashResult seculityCardResult = seculityCardFuture.get();
    const FileHashResult betterAudioResult = betterAudioFuture.get();
    const FileHashResult zoePosterResult = zoePosterFuture.get();
    const FileHashResult snakeHairResult = snakeHairFuture.get();

    // ------------------------------------------------------
    // MGS2: Verify Afevis Bugfix Collection (base) installation
    // ------------------------------------------------------
    if (baseColOrange2Result.exists && !hashEquals(baseColOrange2Result, CBFC_BASE_FLATLIST_WIN_COL_ORANGE2_CTXR_SHA1))
    {
        spdlog::warn("------------------- ! Community Bugfix Compilation (Base) Missing ! -------------------");
        spdlog::warn("Community Bugfix Compilation installation issue detected, base package is NOT found.");
        spdlog::warn("This can occur if Steam has verified integrity and damaged your mod files, or if the Base Bugfix Compilation zip wasn't installed.");
        spdlog::warn("The base package is required for proper functionality, even when 2x & 4x packages are installed.");
        spdlog::warn("Please install the Community Bugfix Compilation -> Base <- package to ensure proper game functionality.");
        spdlog::warn("Please visit our Nexus page at: https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files to download the base package.");
        spdlog::warn("Or our GitHub releases page at: https://github.com/ShizCalev/MGS2-Community-Bugfix-Compilation/releases");
        spdlog::warn("------------------- ! Community Bugfix Compilation (Base) Missing ! -------------------");

        if (int result = MessageBoxA(
            nullptr,
            "Community Bugfix Compilation installation issue detected, base package is NOT found.\n"
            "\n"
            "This can occur if Steam has verified integrity and damaged your mod files, or if the Base Bugfix Compilation zip wasn't installed.\n"
            "\n"
            "The base package is required for proper functionality, even when 2x & 4x packages are installed.\n"
            "Please install the Community Bugfix Compilation -> Base <- package to ensure proper game functionality.\n"
            "\n"
            "Would you like to open the Community Bugfix Nexus download page now to download the base package?\n"
            "(You can also find a link to our GitHub releases on the Nexus page if preferred.)",
            "Community Bugfix Compilation (Base) Missing",
            MB_ICONWARNING | MB_YESNO);
        result == IDYES)
        {
            openCommunityBugfixPage();
        }
    }

    if (ovrStmColOrange2Result.exists)
    {
        // ------------------------------------------------------
        // MGS2: Check if liqmix AI slop packs are installed
        // ------------------------------------------------------
        const bool isLiqMixPack =
            hashEquals(ovrStmColOrange2Result, LIQMIX_SLOP_4X_ORANGE2_CTXR_SHA1) ||
            hashEquals(ovrStmColOrange2Result, LIQMIX_SLOP_2X_ORANGE2_CTXR_SHA1);

        if (isLiqMixPack)
        {
            spdlog::warn("------------------- ! Community Bugfix Compilation - Mod Compatibility Issue ! -------------------");
            spdlog::warn("LiqMix's AI Slop AI Upscaled texture pack has been detected.");
            spdlog::warn("LiqMix's AI Slop texture pack is VERY out of date and has been replaced by the MGS2 Community Bugfix Compilation's Upscaled texture packs, which includes all the texture fixes from the base version.");
            spdlog::warn("Please uninstall LiqMix's AI Slop Upscaled texture pack to ensure proper game functionality.");
            spdlog::warn("Please visit our Nexus page at: https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files to download our upscaled texture package.");
            spdlog::warn("Or our GitHub releases page at: https://github.com/ShizCalev/MGS2-Community-Bugfix-Compilation/releases");
            spdlog::warn("------------------- ! Community Bugfix Compilation - Mod Compatibility Issue ! -------------------");

            if (int result = MessageBoxA(
                nullptr,
                "LiqMix's AI Slop AI Upscaled texture pack has been detected.\n"
                "\n"
                "LiqMix's AI Slop texture pack is VERY out of date and has been replaced by the Community Bugfix Compilation's upscaled packs, which includes all the texture fixes from the base version.\n"
                "Please remove LiqMix's AI Slop Upscaled texture pack to ensure proper game functionality.\n"
                "\n"
                "Would you like to open the Community Bugfix Nexus download page now to download the correct package?\n"
                "(You can also find a link to our GitHub releases on the Nexus page if preferred.)",
                "Community Bugfix Compilation - Mod Compatibility Issue",
                MB_ICONWARNING | MB_YESNO);
                result == IDYES)
            {
                openCommunityBugfixPage();
            }
        }
        // ------------------------------------------------------
        // MGS2: Verify community bugfix upscaled pack is loaded AFTER the base pack
        // ------------------------------------------------------
        else if (hashEquals(ovrStmColOrange2Result, CBFC_4x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1))
        {
            if (seculityCardResult.exists && !hashEquals(seculityCardResult, CBFC_4x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1))
            {
                spdlog::warn("------------------- ! Community Bugfix Compilation (4x Upscaled Pack) Installation Issue ! -------------------");
                spdlog::warn("Community Bugfix Compilation 4x Texture Pack installation issue detected.");
                spdlog::warn("Unable to get the expected texture hash for seculitycard_lv2_alp in the 4x Upscaled pack. This usually means the base package was installed or loaded after the 4x pack.");
                spdlog::warn("The 4x Upscaled pack must be installed or loaded AFTER the base package.");
                spdlog::warn("Please reinstall the 4x Upscaled pack to ensure correct behavior.");
                spdlog::warn("If you are using a mod manager, make sure the 4x Upscaled pack is loaded AFTER the base package.");
                spdlog::warn("Please visit our Nexus page at: https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files to redownload the 4x upscaled package.");
                spdlog::warn("Or our GitHub releases page at: https://github.com/ShizCalev/MGS2-Community-Bugfix-Compilation/releases");
                spdlog::warn("------------------- ! Community Bugfix Compilation (4x Upscaled Pack) Installation Issue ! -------------------");

                if (int result = MessageBoxA(
                    nullptr,
                    "Community Bugfix Compilation 4x Texture Pack installation issue detected.\n"
                    "\n"
                    "Unable to get the expected texture hash for seculitycard_lv2_alp in the 4x Upscaled pack. This usually means the base package was installed or loaded after the 4x pack.\n"
                    "The 4x Upscaled pack must be installed or loaded AFTER the base package.\n"
                    "\n"
                    "Please reinstall the 4x Upscaled pack to ensure correct behavior.\n"
                    "If you are using a mod manager, make sure the 4x Upscaled pack is loaded AFTER the base package.\n"
                    "\n"
                    "Would you like to open the Community Bugfix Nexus download page now to redownload the 4x upscaled package?\n"
                    "(You can also find a link to our GitHub releases on the Nexus page if preferred.)",
                    "Community Bugfix Compilation (4x Upscale) Installation Issue",
                    MB_ICONWARNING | MB_YESNO);
                result == IDYES)
                {
                    openCommunityBugfixPage();
                }
            }
        }
        else if (hashEquals(ovrStmColOrange2Result, CBFC_2x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1))
        {
            if (seculityCardResult.exists && !hashEquals(seculityCardResult, CBFC_2x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1))
            {
                spdlog::warn("------------------- ! Community Bugfix Compilation (2x Upscaled Pack) Installation Issue ! -------------------");
                spdlog::warn("Community Bugfix Compilation 2x Texture Pack installation issue detected.");
                spdlog::warn("Unable to get the expected texture hash for seculitycard_lv2_alp in the 2x Upscaled pack. This usually means the base package was installed or loaded after the 2x pack.");
                spdlog::warn("The 2x Upscaled pack must be installed or loaded AFTER the base package.");
                spdlog::warn("Please reinstall the 2x Upscaled pack to ensure correct behavior.");
                spdlog::warn("If you are using a mod manager, make sure the 2x Upscaled pack is loaded AFTER the base package.");
                spdlog::warn("Please visit our Nexus page at: https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files to redownload the 2x upscaled package.");
                spdlog::warn("Or our GitHub releases page at: https://github.com/ShizCalev/MGS2-Community-Bugfix-Compilation/releases");
                spdlog::warn("------------------- ! Community Bugfix Compilation (2x Upscaled Pack) Installation Issue ! -------------------");

                if (int result = MessageBoxA(
                    nullptr,
                    "Community Bugfix Compilation 2x Texture Pack installation issue detected.\n"
                    "\n"
                    "Unable to get the expected texture hash for seculitycard_lv2_alp in the 2x Upscaled pack. This usually means the base package was installed or loaded after the 2x pack.\n"
                    "The 2x Upscaled pack must be installed or loaded AFTER the base package.\n"
                    "\n"
                    "Please reinstall the 2x Upscaled pack to ensure correct behavior.\n"
                    "If you are using a mod manager, make sure the 2x Upscaled pack is loaded AFTER the base package.\n"
                    "\n"
                    "Would you like to open the Community Bugfix Nexus download page now to redownload the 2x upscaled package?\n"
                    "(You can also find a link to our GitHub releases on the Nexus page if preferred.)",
                    "Community Bugfix Compilation (2x Upscale) Installation Issue",
                    MB_ICONWARNING | MB_YESNO);
                result == IDYES)
                {
                    openCommunityBugfixPage();
                }
            }
        }
    }

    // ------------------------------------------------------
    // MGS2: Verify community bugfix upscaled pack is loaded AFTER better audio mod
    // ------------------------------------------------------
    if (betterAudioResult.exists &&
        (hashEquals(betterAudioResult, BETTER_AUDIO_p010_01_p01g_VAMP_SEAL_SDT_SHA1) ||
         hashEquals(betterAudioResult, VANILLA_p010_01_p01g_VAMP_SEAL_SDT_SHA1)))
    {
        spdlog::warn("------------------- ! Community Bugfix Compilation (Base) - Installation Issue ! -------------------");
        spdlog::warn("Community Bugfix Compilation installation issue detected!");
        spdlog::warn("Unexpected SHA-1 hash for p010_01_p01g.sdt.");
        spdlog::warn("This can occur if Steam has verified integrity and damaged your mod files, or if the Community Bugfix Compilation (Base) was loaded BEFORE KnightKiller's Better Audio Mod.");
        spdlog::warn("Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.");
        spdlog::warn("If you are using a mod manager, make sure Community Bugfix Compilation (Base) is loaded AFTER Better Audio Mod.");
        spdlog::warn("Please visit our Nexus page at: https://www.nexusmods.com/metalgearsolid2mc/mods/52?tab=files to redownload the base package.");
        spdlog::warn("Or our GitHub releases page at: https://github.com/ShizCalev/MGS2-Community-Bugfix-Compilation/releases");
        spdlog::warn("------------------- ! Community Bugfix Compilation (Base) Missing ! -------------------");

        if (int result = MessageBoxA(
            nullptr,
            "Community Bugfix Compilation installation issue detected!\n"
            "\n"
            "Unexpected SHA-1 hash for p010_01_p01g.sdt.\n"
            "This can occur if Steam has verified integrity and damaged your mod files, or if the Community Bugfix Compilation (Base) was loaded BEFORE KnightKiller's Better Audio Mod.\n"
            "\n"
            "Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.\n"
            "If you are using a mod manager, make sure Community Bugfix Compilation (Base) is loaded AFTER Better Audio Mod.\n"
            "\n"
            "Would you like to open the Community Bugfix Nexus download page now to download the base package?\n"
            "(You can also find a link to our GitHub releases on the Nexus page if preferred.)",
            "Community Bugfix Compilation installation issue",
            MB_ICONWARNING | MB_YESNO);
        result == IDYES)
        {
            openCommunityBugfixPage();
        }
    }

    // ------------------------------------------------------
    // MGS2: Check if Higher Resolution KojiPro posters mod is installed
    // ------------------------------------------------------
    if (zoePosterResult.exists && hashEquals(zoePosterResult, HIGHER_RES_KOJIPRO_ZOE_POSTER_CTXR_SHA1))
    {
        spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
        spdlog::warn("Community Bugfix Compilation installation issue detected.");
        spdlog::warn("j1llm4r13's Higher Resolution KojiPro Posters mod has been detected.");
        spdlog::warn("This mod has been replaced by the Community Bugfix Compilation, which hand-remakes the original source assets.");
        spdlog::warn("We already override the old mod's files, so we're just noting that it's unneeded here. <3");
        spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
    }

    // ------------------------------------------------------
    // MGS2: Check if guy on a chair hair fix is installed
    // ------------------------------------------------------
    if (snakeHairResult.exists &&
        (hashEquals(snakeHairResult, GUYONACHAIR_HAIRFIX_SNA_HAIR3_V2_CTXR_SHA1) ||
         hashEquals(snakeHairResult, GUYONACHAIR_HAIRFIX_SNA_HAIR3_V1_CTXR_SHA1)))
    {
        spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
        spdlog::warn("Community Bugfix Compilation installation issue detected.");
        spdlog::warn("Guy on a Chair's Snake hair fix mod has been detected.");
        spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.");
        spdlog::warn("Leftover mod files have been cleaned up.");
        spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
    }


}

