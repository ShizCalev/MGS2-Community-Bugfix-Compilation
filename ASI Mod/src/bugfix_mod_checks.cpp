// ReSharper disable CppUseAuto
// ReSharper disable IdentifierTypo
#include "stdafx.h"
#include "bugfix_mod_checks.hpp"

#include "common.hpp"
#include "logging.hpp"
#include "version.h"


//Community Bugfix hashes
constexpr const char* CBFC_BASE_FLATLIST_WIN_chr1_05_alp_sub_ovl_CTXR_SHA1 = "b4c6895d80d7aed75f35bf6fe4c57a7887ce0aa0";
constexpr const char* CBFC_2x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1 = "59aadac25f41712a2b02cdcc71d5ca814c2deee4";
constexpr const char* CBFC_4x_OVRSTM_WIN_COL_ORANGE2_CTXR_SHA1 = "91ccce1dff9d9c6e46915e49534764ab5561e15e";


constexpr const char* CBFC_2x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1 = "1e2979a1ebd2f781f3b7ca4e232ca62be9bb84be";
constexpr const char* CBFC_4x_BUGFIXED_seculitycard_lv2_alp_CTXR_SHA1 = "7d49ba9afaa1ea4eea7195abcbb0561afa401c27";



//Third party mod file hashes.
constexpr const char* LIQMIX_SLOP_4X_ORANGE2_CTXR_SHA1 = "4ecda248b079ee426262a23b64df6cb05a249088";
constexpr const char* LIQMIX_SLOP_2X_ORANGE2_CTXR_SHA1 = "96ba1191c0da112d355bf510dcb3828f1183d1b5";

constexpr const char* HIGHER_RES_KOJIPRO_ZOE_POSTER_CTXR_SHA1 = "ce3fe5bd55aebb046103b5dba1cffa736b08abd2";

constexpr const char* GUYONACHAIR_HAIRFIX_V1_sna_hair1_alp_ovl_CTXR_SHA1 = "ac57554dd8fd091650c39c6698e551890af7cab1";
constexpr const char* GUYONACHAIR_HAIRFIX_V1_sna_hair2dt_alp_ovl_CTXR_SHA1 = "862e917ccaf23e9bc9f7f841fe84dda00c70814b";

constexpr const char* GUYONACHAIR_HAIRFIX_V2_sna_hair1_alp_ovl_CTXR_SHA1 = "7daf7a08fc41da6d2697315db62de1b44a55d84d";
constexpr const char* GUYONACHAIR_HAIRFIX_V2_sna_hair2_alp_ovl_CTXR_SHA1 = "3042e939b7900fc0d9afa84a51d13864336c3b52";
constexpr const char* GUYONACHAIR_HAIRFIX_V2_sna_hair2dt_alp_ovl_CTXR_SHA1 = "1944c45397ef15c5a4b4d29f7ef34dc43774a958";
constexpr const char* GUYONACHAIR_HAIRFIX_V2_sna_hair3_CTXR_SHA1 = "606cbad8a8b3e850b9a8b76f944bc3be25ed5f69";

constexpr const char* BETTER_AUDIO_p010_01_p01g_VAMP_SEAL_SDT_SHA1 = "3424163081275d9152b162d648b82616d3100ab1";

constexpr const char* AFEVIS_OLD_DECENSOR_EU_STAGE_D04T_BP_MANIFEST_SHA1 = "eaaee5d1c8d746994ee5dc47004a98448fe5c7b5";

//Vanilla game hashes
constexpr const char* VANILLA_p010_01_p01g_VAMP_SEAL_SDT_SHA1 = "301dcbda56107c7d5617a98256369abbb2b94fee";

// todo - do all this shit in futures
// detect outdated ui files
// 

namespace
{


    std::string Sha1ToString(const std::optional<std::array<std::uint8_t, 20>>& sha1)
    {
        if (!sha1.has_value())
        {
            return {};
        }

        std::ostringstream oss;
        oss << std::hex << std::setfill('0');

        for (std::uint8_t b : *sha1)
        {
            oss << std::setw(2) << static_cast<int>(b);
        }

        return oss.str();
    }
}



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

    const std::filesystem::path baseChr1_05_alp_sub_ovl2Path = sExePath / "textures" / "flatlist" / "_win" / "chr1_05_alp_sub_ovl.bmp.ctxr";
    const std::filesystem::path ovrStmColOrange2Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "col_orange2.bmp.ctxr";
    const std::filesystem::path seculityCardPath = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "seculitycard_lv2_alp.bmp.ctxr";
    const std::filesystem::path betterAudioCheckPath = sExePath / "us" / "demo" / "_bp" / "p010_01_p01g.sdt";
    const std::filesystem::path zoePosterPath = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "zoe_pos_n.bmp.ctxr";

    const std::filesystem::path snakeHair1_Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair1_alp_ovl.bmp.ctxr";
    const std::filesystem::path snakeHair2_Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair2_alp_ovl.bmp.ctxr";
    const std::filesystem::path snakeHair2DT_Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair2dt_alp_ovl.bmp.ctxr";
    const std::filesystem::path snakeHair3_Path = sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair3.bmp.ctxr";

    const std::filesystem::path v1_snakeHair1_Path = sExePath / "textures" / "flatlist" / "_win" / "sna_hair1_alp_ovl.bmp.ctxr";
    const std::filesystem::path v1_snakeHair2DT_Path = sExePath / "textures" / "flatlist" / "_win" / "sna_hair2dt_alp_ovl.bmp.ctxr";

    const std::filesystem::path afevis_old_decensor_d04t_manifest_Path = sExePath / "eu" / "stage" / "d04t" / "bp_assets.txt";


    const auto hashEquals =
        [](const FileHashResult& result, const char* expected) -> bool
        {
            return result.exists && result.sha1.has_value() && Util::SHA1Equals(*result.sha1, expected);
        };

    auto baseChr1_05_alp_sub_ovl2Future = startHashTask(baseChr1_05_alp_sub_ovl2Path);
    auto ovrStmColOrange2Future = startHashTask(ovrStmColOrange2Path);
    auto seculityCardFuture = startHashTask(seculityCardPath);
    auto betterAudioFuture = startHashTask(betterAudioCheckPath);
    auto zoePosterFuture = startHashTask(zoePosterPath);
    auto snakeHair1_Future = startHashTask(snakeHair1_Path);
    auto snakeHair2_Future = startHashTask(snakeHair2_Path);
    auto snakeHair2DT_Future = startHashTask(snakeHair2DT_Path);
    auto snakeHair3_Future = startHashTask(snakeHair3_Path);
    auto v1_snakeHair1_Future = startHashTask(v1_snakeHair1_Path);
    auto v1_snakeHair2DT_Future = startHashTask(v1_snakeHair2DT_Path);
    auto afevisOldDecensorD04TManifest_Future = startHashTask(afevis_old_decensor_d04t_manifest_Path);

    const FileHashResult baseChr1_05_alp_sub_ovl2Result = baseChr1_05_alp_sub_ovl2Future.get();
    const FileHashResult ovrStmColOrange2Result = ovrStmColOrange2Future.get();
    const FileHashResult seculityCardResult = seculityCardFuture.get();
    const FileHashResult betterAudioResult = betterAudioFuture.get();
    const FileHashResult zoePosterResult = zoePosterFuture.get();
    const FileHashResult snakeHair1_Result = snakeHair1_Future.get();
    const FileHashResult snakeHair2_Result = snakeHair2_Future.get();
    const FileHashResult snakeHair2DT_Result = snakeHair2DT_Future.get();
    const FileHashResult snakeHair3_Result = snakeHair3_Future.get();
    const FileHashResult v1_snakeHair1_Result = v1_snakeHair1_Future.get();
    const FileHashResult v1_snakeHair2DT_Result = v1_snakeHair2DT_Future.get();
    const FileHashResult afevisOldDecensorD04TManifest_Result = afevisOldDecensorD04TManifest_Future.get();


    // ------------------------------------------------------
    // MGS2: Verify Afevis Bugfix Collection (base) installation
    // ------------------------------------------------------
    if (baseChr1_05_alp_sub_ovl2Result.exists && !hashEquals(baseChr1_05_alp_sub_ovl2Result, CBFC_BASE_FLATLIST_WIN_chr1_05_alp_sub_ovl_CTXR_SHA1))
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
        (hashEquals(betterAudioResult, BETTER_AUDIO_p010_01_p01g_VAMP_SEAL_SDT_SHA1) || hashEquals(betterAudioResult, VANILLA_p010_01_p01g_VAMP_SEAL_SDT_SHA1)))
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

    //snakeHair1_Result is the community bugfixed file. the rest are leftovers
    { 
        const FileHashResult* detected = nullptr;

        if (snakeHair1_Result.exists &&
            (hashEquals(snakeHair1_Result, GUYONACHAIR_HAIRFIX_V1_sna_hair1_alp_ovl_CTXR_SHA1) ||
             hashEquals(snakeHair1_Result, GUYONACHAIR_HAIRFIX_V2_sna_hair1_alp_ovl_CTXR_SHA1)))
        {
            detected = &snakeHair1_Result;
        }
        else if (v1_snakeHair1_Result.exists &&
                 hashEquals(v1_snakeHair1_Result, GUYONACHAIR_HAIRFIX_V1_sna_hair1_alp_ovl_CTXR_SHA1))
        {
            detected = &v1_snakeHair1_Result;
        }
        else if (v1_snakeHair2DT_Result.exists &&
                 hashEquals(v1_snakeHair2DT_Result, GUYONACHAIR_HAIRFIX_V1_sna_hair2dt_alp_ovl_CTXR_SHA1))
        {
            detected = &v1_snakeHair2DT_Result;
        }

        if (detected)
        {
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            spdlog::warn("Community Bugfix Compilation installation issue detected.");

            // handle optional sha1 safely
            std::string sha1Str = detected->sha1
                ? Sha1ToString(*detected->sha1)
                : "NO_SHA1";

            spdlog::warn("Guy on a Chair's Snake hair fix mod has been detected. ({} - {})",
                         detected->path.string(), sha1Str);

            spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.");
            spdlog::warn("Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.");
            spdlog::warn("Or, if you are using a mod manager, please remove Guy on a Chair's Snake hair fix mod.");
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");

            Logging::ShowConsole();

            std::cout << "Community Bugfix Compilation installation issue detected.\n"
                "----------------------------------------\n"
                "Guy on a Chair's Snake hair fix mod has been detected.\n"
                "(" << detected->path.string() << " - " << sha1Str << ")\n\n"
                "This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.\n\n"
                "Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.\n"
                "Or, if you are using a mod manager, please remove Guy on a Chair's Snake hair fix mod."
                << std::endl;
        }

        if (snakeHair2_Result.exists && (hashEquals(snakeHair2_Result, GUYONACHAIR_HAIRFIX_V2_sna_hair2_alp_ovl_CTXR_SHA1)))
        {
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            spdlog::warn("Community Bugfix Compilation installation issue detected.");
            spdlog::warn("Leftover files from Guy on a Chair's Snake hair fix mod has been detected.");
            spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.");
            spdlog::warn("Removing leftover file: {}", snakeHair2_Result.path.string());
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            std::filesystem::remove(snakeHair2_Result.path);
        }

        if (snakeHair2DT_Result.exists && (hashEquals(snakeHair2DT_Result, GUYONACHAIR_HAIRFIX_V1_sna_hair2dt_alp_ovl_CTXR_SHA1) || hashEquals(snakeHair2DT_Result, GUYONACHAIR_HAIRFIX_V2_sna_hair2dt_alp_ovl_CTXR_SHA1)))
        {
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            spdlog::warn("Community Bugfix Compilation installation issue detected.");
            spdlog::warn("Leftover files from Guy on a Chair's Snake hair fix mod has been detected.");
            spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.");
            spdlog::warn("Removing leftover file: {}", snakeHair2DT_Result.path.string());
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            std::filesystem::remove(snakeHair2DT_Result.path);
        }

        if (snakeHair3_Result.exists && (hashEquals(snakeHair3_Result, GUYONACHAIR_HAIRFIX_V2_sna_hair3_CTXR_SHA1)))
        {
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            spdlog::warn("Community Bugfix Compilation installation issue detected.");
            spdlog::warn("Leftover files from Guy on a Chair's Snake hair fix mod has been detected.");
            spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Mod and the standalone version is no longer required.");
            spdlog::warn("Removing leftover file: {}", snakeHair3_Result.path.string());
            spdlog::warn("------------------- ! Community Bugfix Compilation - Installation Issue ! -------------------");
            std::filesystem::remove(snakeHair3_Result.path);
        }
    }


    // ------------------------------------------------------
    // Afevis's Sons of Liberty Restoration - Decensorship and Music Restoration
    // ------------------------------------------------------

    if (afevisOldDecensorD04TManifest_Result.exists && hashEquals(afevisOldDecensorD04TManifest_Result, AFEVIS_OLD_DECENSOR_EU_STAGE_D04T_BP_MANIFEST_SHA1))
    {
        spdlog::warn("------------------- ! Afevis's Sons of Liberty Restoration - Old Decensor Detected ! -------------------");
        spdlog::warn("Afevis's Sons of Liberty Restoration - Decensorship and Music Restoration mod has been detected.");
        spdlog::warn("This mod has been integrated directly into the MGS2 Community Bugfix Compilation, which includes the decensor and music restoration for all versions of the game.");
        spdlog::warn("Installing the outdated version of the decensor mod after the Community Bugfix Compilation can cause crashes.");
        spdlog::warn("Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.");
        spdlog::warn("Or, if you are using a mod manager, please remove Afevis's Sons of Liberty Restoration - Decensorship and Music Restoration mod.");
        spdlog::warn("------------------- ! Afevis's Sons of Liberty Restoration - Old Decensor Detected ! -------------------");
        

        MessageBoxA(nullptr,
            "Community Bugfix Compilation installation issue detected\n"
            "----------------------------------------\n"
            "Afevis's Sons of Liberty Restoration - Decensorship and Music Restoration mod has been detected.\n"
            "\n"
            "This mod has been integrated directly into the MGS2 Community Bugfix Compilation, which includes the decensor and music restoration for all versions of the game.\n"
            "Installing the outdated version of the decensor mod after the Community Bugfix Compilation can cause crashes.\n"
            "\n"
            "Please reinstall the Community Bugfix Compilation (Base) to ensure correct behavior.\n"
            "Or, if you are using a mod manager, please remove Afevis's Sons of Liberty Restoration - Decensorship and Music Restoration mod.",
            "Community Bugfix Compilation Installation Issue",
            MB_ICONWARNING | MB_OK);
    }



}

