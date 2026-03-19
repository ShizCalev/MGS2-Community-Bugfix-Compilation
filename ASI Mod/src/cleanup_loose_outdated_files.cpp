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
}
