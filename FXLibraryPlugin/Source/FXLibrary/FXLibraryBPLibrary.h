#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "FXLibraryBPLibrary.generated.h"

// Exposes engine-level helpers to Python (things Python cannot do directly in UE 5.1).
UCLASS()
class UFXLibraryBPLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// Render the engine-generated thumbnail of an asset to a PNG file.
	// Returns false if no thumbnail exists yet (open the asset once in the Content Browser first).
	UFUNCTION(BlueprintCallable, Category = "FX Library")
	static bool ExportAssetThumbnail(UObject* Asset, const FString& OutputImagePath);
};
