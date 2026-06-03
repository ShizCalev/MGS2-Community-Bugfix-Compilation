

WIP:


Textures:

Folder structure is laid out as so:

Texture Fixes Folder

	/Chains		= AI Upscaling preset files & UI conversion script.
	
	/mc textures	 = all vanilla Bluepoint/Konami remastered master collection textures, sturctured by their metadata. 
		This folder is ONLY vanilla files. this directory generally shouldn't need to be touched.
		
	/ps2 textures	 = all PS2 textures, again, structured by metadata, mipmap requirements, alpha vs opaque, ect. 
		These are pulled directly from the MGS2-PS2-Textures repo. this directory generally shouldn't need to be touched.
		
	/Self Remade	 = all texture bugfixes, remade textures, ect.
		All texture contributions should be added here.
	
	/Staging	= Live CTXR files. These are zipped by the create release workflow.
		These textures are all generated via _staging_main.py. 
		
		Each "_win" folder inside of staging has several metadata txt/csv's:
		
			conversion_hashes.csv
				Automatically generated record containing all metadata for every generated ctxr file
				Metadata icludes original png/tga sha1, the ctxr's sha1, if it has mipmaps, if opacity has been stripped, and what version of the upscaler & staging scripts it was generated with.
				
			folders to process.txt
				List of all TGA/PNG folder paths that will be included in this folder.
				
				Example: flatlist/_win pulls only from MC & PS2 texture sources.
						flatlist/ovr_stm/_win pulls from upscaled texture sources
						flatlist/ovr_stm/ovr_** pulls from "Self Remade" / custom texture sources (so that these textures always override upscaled textures.)
	
	/Staging - 2x Upscaled	= Live CTXR files, gets zipped into the 2x Upscaled addon pack.
	
	/Staging - 4x Upscaled	= Live CTXR files, gets zipped into the 2x Upscaled addon pack.
	
	
	lod_replacement_mapping.csv	= WIP: A hundred or so textures are lower quality / psuedo-mipmap versions of other textures used on LOD models at a distance as a memory optimization for the PS2.
		Files listed in here will be replaced by their higher quality version by _staging_main.py
		
	force_extra_upscale_smoothing.txt	= List of file stems for textures that upscale poorly with base Remarci_4x. These are mostly PS2 textures that make heavy usage of dithering (typically face textures.)
		Files listed in here will be upscaled with Remarci_4x_Extra instead, which is closer to a bilinear upscaler.
		
	never_upscale.txt	= crap that doesn't upscale well. Water textures and some UI elements are always rendered at full size, and should not be upscaled.
	
	no_mip_regex.txt	= Regex matches for atlas textures, specular maps, and UI textures. 
		Textures with matching names will be generated without mipmaps.
		(Vanilla UI textures already do not have mips - all other textures are bugfixes.)
		
	shadow_map_stems.txt 	= more crap that doesn't upscale well. Shadow maps tend to lose a lot of fine details when upscaled.

----------------------	
	
Scripts:
	_launch_ctxr3.py	= generates UI textures from a given input folder. This utilizes a heavily cut down texture conversion script (Chains/ctxr_cli.py)
	
	_staging_main.py	= per-staging folder processing script.
		
		this is where 95% of the magic happens.
		
		parses all metadata for each conversion_hashes.csv in every _win folder.
		checks if any textures in "folders to process.txt"'s paths have changed. if they have, the mismatched ctxr will be deleted, and a new one will be generated.
		
		checks no_mip_regex to decide if a texture should have mips
		opacity is based on ps2 metadata in https://github.com/dotlessone/MGS2-PS2-Textures/blob/main/Tri-Dumped/Master%20Collection/Metadata/mgs2_mc_tri_dumped_metadata.csv
		
		Textures are finally converted to DDS with Nvidia Texture Tool, upscaled with chainner (for upscaled packs), and finally, converted to CTXR using CTXR3 (update not yet published.)
				
	
	find all textures from tri strcode.py	= support script.
		========================================================================
		MGS2 Texture Map Lookup
		========================================================================
		1. Find unique textures from tri strcode
		2. Find unique textures from texture strcode
		3. Find unique textures from stage
		4. Find unique textures from tri / texture strcode pair
		5. Find all tri / texture strcode pairs containing texture
		6. Find all tri / texture strcode pairs that map to multiple textures
		7. Find all textures that map to multiple tri / texture strcode pairs
		
	Search for shadow maps.py	= generates single_color_rgb_stems_report.txt, used for locating shadow_map_stems.


	Update Staging.py	=	the other 5% of the magic.
		Processes all STAGING_ROOTS (local community bugfix, upscaled UI textures, and demastered repos), running _staging_main.py each of their staging folders sequentially.
		This ensures that all newly added community bugfixed textures have an equivalent texture in the demaster pack to keep it at PS2 quality.
		
		Automatically syncs all "folders to process.txt" files from the "Staging - 4x Upscaled" folder to "Staging - 2x Upscaled"
		
		At the end of processing, it'll also sync all files to my local vortex folders for quick verification.
		
----------------------

Self Remade folder:
As mentioned above, this is where all edited texture files live. 
Finished textures / commits should be made into the "Finalized" folder, everything outside of it is considered WIP.

Finalized Structure:

Main folder:
	Images here are fixes for Bluepoint's remastered textures, which were correct in the PS2 version of the game.
	DEMASTER BEHAVIOR: Any files in this folder will automatically be replaced with their PS2 versions.
	UPSCALE BEHAVIOR: These files will all be upscaled for the upscaled packs.
	
"Dont demaster" folder:
	Fixes for textures that were NOT remastered by Bluepoint / are still their original PS2 versions.
	This won't be included in the demaster package, as the CBFC is already considered a prereq. 
	UPSCALE BEHAVIOR: These files will all be upscaled for the upscaled packs.
	
	/Dont Demaster/Dont upscale
		Things that don't upscale well. These won't be included in upscaled packages / will use the version from the Base package.
		
	/Dont Demaster/UI
		UI files. These get generated without mips.
		
"Not Demaster Fixed" folder:
	Fixes for texture bugs that were present in both PS2 & HDC/MC.
	DEMASTER BEHAVIOR: Top level folder gets skipped by the Demastered packs. 
	
	/Not Demaster Fixed/Demaster Fixed
		Sorry for the confusing name. These are PS2 fixed versions of textures for the Demaster pack. 
		These will eventually be backported for a PCSX2 package someday.
	
		
