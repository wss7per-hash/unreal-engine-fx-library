using UnrealBuildTool;

public class FXLibrary : ModuleRules
{
	public FXLibrary(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"CoreUObject",
			"Engine",
			"UnrealEd",          // FThumbnailManager, editor utilities
			"Slate",
			"SlateCore",
			"EditorStyle",
			"AssetTools",
			"AssetRegistry",
			"ContentBrowser",
			"LevelEditor",
			"Blutility",         // EditorUtilityLibrary (C++)
			"PythonScriptPlugin",// run py scripts from C++
			"ImageWrapper",      // encode PNG thumbnail
			"Projects"           // IPluginManager
		});
	}
}
