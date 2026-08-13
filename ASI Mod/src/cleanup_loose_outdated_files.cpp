// ReSharper disable CppUseAuto
// ReSharper disable IdentifierTypo
#include "stdafx.h"
#include "cleanup_loose_outdated_files.hpp"

#include "common.hpp"
#include "helper.hpp"

#include "update_hashes_v2_0_2_to_v2_1_2.hpp"
#include "update_hashes_v2_1_0_to_v2_1_1.hpp"
#include "update_hashes_v2_1_1_to_v2_1_2.hpp"


void CleanupOutdatedModfiles::Check()
{
    if (!(eGameType & MGS2))
    {
        return;
    }


    {   // v2.0.2 -> v2.1.2 | sentinel = sna_shadow.bmp
        static_assert(std::size(kRemoved_Fixes_4x_v2_0_2_to_v2_1_2) == 2648, "kRemoved_Fixes_4x_v2_1_1_to_v2_1_2 count changed");
        static_assert(std::size(kRemoved_Fixes_2x_v2_0_2_to_v2_1_2) == 2648, "kRemoved_Fixes_2x_v2_1_1_to_v2_1_2 count changed");

        const std::filesystem::path baseDir = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win";

        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_4x_v2_0_2_to_v2_1_2), "leftover 4x upscaled textures from v2.0.2 -> v2.1.2 update");
        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_2x_v2_0_2_to_v2_1_2), "leftover 2x upscaled textures from v2.0.2 -> v2.1.2 update");
    }

    {   // v2.1.0 -> v2.1.1 | sentinel = w10a_fogsky_01.bmp
        static_assert(std::size(kRemoved_Fixes_4x_v2_1_0_to_v2_1_1) == 45, "kRemoved_Fixes_4x_v2_1_1_to_v2_1_2 count changed");
        static_assert(std::size(kRemoved_Fixes_2x_v2_1_0_to_v2_1_1) == 45, "kRemoved_Fixes_2x_v2_1_1_to_v2_1_2 count changed");

        const std::filesystem::path baseDir = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win";

        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_4x_v2_1_0_to_v2_1_1), "leftover 4x upscaled textures from v2.1.0 -> v2.1.1 update");
        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_2x_v2_1_0_to_v2_1_1), "leftover 2x upscaled textures from v2.1.0 -> v2.1.1 update");
    }

    {   // v2.1.1 -> v2.1.2 | sentinel = sna_shadow.bmp
        static_assert(std::size(kRemoved_Fixes_4x_v2_1_1_to_v2_1_2) == 2602, "kRemoved_Fixes_4x_v2_1_1_to_v2_1_2 count changed");
        static_assert(std::size(kRemoved_Fixes_2x_v2_1_1_to_v2_1_2) == 2602, "kRemoved_Fixes_2x_v2_1_1_to_v2_1_2 count changed");

        const std::filesystem::path baseDir = sExePath / "textures" / "flatlist" / "ovr_stm" / "_win";

        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_4x_v2_1_1_to_v2_1_2), "leftover 4x upscaled textures from v2.1.1 -> v2.1.2 update");
        Util::RemoveMatchedCtxrFilesWithSentinelLast(baseDir, std::span<const CtxrHashEntry>(kRemoved_Fixes_2x_v2_1_1_to_v2_1_2), "leftover 2x upscaled textures from v2.1.1 -> v2.1.2 update");
    }

    {
    
        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "00c6df98d129bd2f59d785a3f9ad01c39dab7f92", // MGS2 Community Bugfix Compilation - Base v2.1.0-v2.2.0
            "804f5fe55b528e3e072ea12b7f272923924ef641", // MGS2-Demastered-Sub Base 2x AI Upscaled v1.0.3-v1.0.4
            "22bc57896b5e7d3a48432eb148076a8682e45d04", // MGS2-Demastered-Sub Base 4x AI Upscaled v1.0.3-v1.0.4
            "92a9845727c817cb50a300a27236a75ef96ffd4b", // MGS2-Demastered-Sub Base 2x/4x AI Upscaled and PS2 Resolution v1.0.5-v1.0.6
            "3915b9cc8c7071ab8f00433e9d60ea00cf1c3918", // MGS2-Demastered-Sub Base 2x/4x AI Upscaled and PS2 Resolution v1.1.0
            "78ba13e260ec90192931881ff32ef75f41013ebd", // MGS2-Demastered-Sub Base PS2 Resolution v1.0.3-v1.0.4
            "7daf7a08fc41da6d2697315db62de1b44a55d84d"  // Solid Snake Hair Fix v2-10-2-1751534633
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "00c6df98d129bd2f59d785a3f9ad01c39dab7f92", // MGS2 Community Bugfix Compilation - Base v2.1.0-v2.2.0
            "804f5fe55b528e3e072ea12b7f272923924ef641", // MGS2-Demastered-Sub Base 2x AI Upscaled v1.0.3-v1.0.4
            "22bc57896b5e7d3a48432eb148076a8682e45d04", // MGS2-Demastered-Sub Base 4x AI Upscaled v1.0.3-v1.0.4
            "92a9845727c817cb50a300a27236a75ef96ffd4b", // MGS2-Demastered-Sub Base 2x/4x AI Upscaled and PS2 Resolution v1.0.5-v1.0.6
            "3915b9cc8c7071ab8f00433e9d60ea00cf1c3918", // MGS2-Demastered-Sub Base 2x/4x AI Upscaled and PS2 Resolution v1.1.0
            "3682622202b5280032a9c805cf1b43a88aab6618"  // MGS2-Demastered-Sub Base PS2 Resolution v1.0.3-v1.0.4
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR2_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "3042e939b7900fc0d9afa84a51d13864336c3b52" // Solid Snake Hair Fix v2-10-2-1751534633
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR2DT_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "1944c45397ef15c5a4b4d29f7ef34dc43774a958" // Solid Snake Hair Fix v2-10-2-1751534633
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR3_BMP_CTXR_SHA1S[] =
        {
            "606cbad8a8b3e850b9a8b76f944bc3be25ed5f69" // Solid Snake Hair Fix v2-10-2-1751534633
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_W42A_2F_HANGER_01_BMP_CTXR_SHA1S[] =
        {
            "aac25c8b654a4f357980694f466538d254569e6c", // MGS2 Community Bugfix Compilation - Base v2.0.2-v2.1.3
            "9b2966b4a18863bcb4dcd34ab74f6ecab7c8952e", // MGS2 Community Bugfix Compilation - Base v2.2.0
            "5d4670514e045a726208504dc72a30598ed459b9", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.0.2
            "4445e8b717d68c0274a50591eb397909e6787171", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.1.0-v2.1.3
            "cbfa0aa131b659785605e41ab4e5a147170b3581", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.2.0
            "9335715f4907ae7da3b801123e4cb4967f346fc8", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.0.2
            "6f7d26177e4a9451123e51d358364c15d6646e35", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.1.0-v2.1.3
            "2742026943ef52c43d92b4ba97a332d61fcf29f7"  // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.2.0
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_W42A_2F_HANGER_01_BMP_CTXR_SHA1S[] =
        {
            "aac25c8b654a4f357980694f466538d254569e6c", // MGS2 Community Bugfix Compilation - Base v2.0.2-v2.1.3
            "9b2966b4a18863bcb4dcd34ab74f6ecab7c8952e", // MGS2 Community Bugfix Compilation - Base v2.2.0
            "4445e8b717d68c0274a50591eb397909e6787171", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.1.0-v2.1.3
            "cbfa0aa131b659785605e41ab4e5a147170b3581", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.2.0
            "6f7d26177e4a9451123e51d358364c15d6646e35", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.1.0-v2.1.3
            "2742026943ef52c43d92b4ba97a332d61fcf29f7"  // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.2.0
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_W42A_2F_HANGER_01_BMP_93C338D289B2B6BF19A677E84199A633_CTXR_SHA1S[] =
        {
            "56e3c5c91e4467501b17a9b04419ea20c7e3e23b", // MGS2 Community Bugfix Compilation - Base v2.0.2-v2.1.3
            "95b04e979aea72101ba7727366a50f468fe97a73", // MGS2 Community Bugfix Compilation - Base v2.2.0
            "51d92d8605ce9b70aa3fb3a9ff5b99a4e398fd33", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.0.2
            "5e26e41e1e08dd8b5348e54b2fe92e31711527c1", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.1.0-v2.1.3
            "feff754990af813fd36925976b3c0f79fac52e77", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.2.0
            "8056494997b190eb9647bdec9684f1017ab18ab0", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.0.2
            "d5b3ed6453bdd715a4c0d733d4da06a509feb9ad", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.1.0-v2.1.3
            "6953085bfe4c28b70b132031e05b683518f0fb1f"  // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.2.0
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_W42A_2F_HANGER_01_BMP_93C338D289B2B6BF19A677E84199A633_CTXR_SHA1S[] =
        {
            "56e3c5c91e4467501b17a9b04419ea20c7e3e23b", // MGS2 Community Bugfix Compilation - Base v2.0.2-v2.1.3
            "95b04e979aea72101ba7727366a50f468fe97a73", // MGS2 Community Bugfix Compilation - Base v2.2.0
            "5e26e41e1e08dd8b5348e54b2fe92e31711527c1", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.1.0-v2.1.3
            "feff754990af813fd36925976b3c0f79fac52e77", // MGS2 Community Bugfix Compilation - 2x Upscaled Addon v2.2.0
            "d5b3ed6453bdd715a4c0d733d4da06a509feb9ad", // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.1.0-v2.1.3
            "6953085bfe4c28b70b132031e05b683518f0fb1f"  // MGS2 Community Bugfix Compilation - 4x Upscaled Addon v2.2.0
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "7daf7a08fc41da6d2697315db62de1b44a55d84d", // Guyonachair Solid Snake Hair Fix v2 ovr stm
            "ac57554dd8fd091650c39c6698e551890af7cab1", // Guyonachair Solid Snake Hair Fix-1 ovr stm
        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR2DT_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "1944c45397ef15c5a4b4d29f7ef34dc43774a958", // Guyonachair Solid Snake Hair Fix v2 ovr stm
            "862e917ccaf23e9bc9f7f841fe84dda00c70814b", // Guyonachair Solid Snake Hair Fix-1 ovr stm

        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR2_ALP_OVL_BMP_CTXR_SHA1S[] =
        {
            "3042e939b7900fc0d9afa84a51d13864336c3b52", // Guyonachair Solid Snake Hair Fix v2 ovr stm
            "68ab590796fd3849d64a7fa2c7c93960f2b89f30", // Guyonachair Solid Snake Hair Fix-1 ovr stm

        };

        constexpr const char* TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR3_BMP_CTXR_SHA1S[] =
        {
            "606cbad8a8b3e850b9a8b76f944bc3be25ed5f69", // Guyonachair Solid Snake Hair Fix v2 ovr stm
            "f8ae30ee716bd43ed7af1e5b8d78a93d32711668", // Guyonachair Solid Snake Hair Fix-1 ovr stm
        };

    
        const Util::RemoveFileEntry outdatedFiles[] =
        {

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "sna_hair1_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "sna_hair2dt_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR2DT_ALP_OVL_BMP_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "sna_hair2_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR2_ALP_OVL_BMP_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "_win" / "sna_hair3.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_WIN_SNA_HAIR3_BMP_CTXR_SHA1S },


            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair1_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_jp" / "_win" / "sna_hair1_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_SNA_HAIR1_ALP_OVL_BMP_CTXR_SHA1S },

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair2_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR2_ALP_OVL_BMP_CTXR_SHA1S },

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair2dt_alp_ovl.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR2DT_ALP_OVL_BMP_CTXR_SHA1S },

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "sna_hair3.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_SNA_HAIR3_BMP_CTXR_SHA1S },

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_jp" / "_win" / "w42a_2f_hanger_01.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_W42A_2F_HANGER_01_BMP_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "w42a_2f_hanger_01.bmp.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_W42A_2F_HANGER_01_BMP_CTXR_SHA1S },

            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_eu" / "_win" / "w42a_2f_hanger_01.bmp_93c338d289b2b6bf19a677e84199a633.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_EU_WIN_W42A_2F_HANGER_01_BMP_93C338D289B2B6BF19A677E84199A633_CTXR_SHA1S },
            {sExePath / "textures" / "flatlist" / "ovr_stm" / "ovr_jp" / "_win" / "w42a_2f_hanger_01.bmp_93c338d289b2b6bf19a677e84199a633.ctxr", TEXTURES_FLATLIST_OVR_STM_OVR_JP_WIN_W42A_2F_HANGER_01_BMP_93C338D289B2B6BF19A677E84199A633_CTXR_SHA1S }
        };

        Util::RemoveMatchingFiles(outdatedFiles, "outdated mod files");
    }

}
