#include "FXLibraryBPLibrary.h"

#include "ObjectTools.h"
#include "IImageWrapperModule.h"
#include "IImageWrapper.h"
#include "Modules/ModuleManager.h"
#include "Misc/FileHelper.h"

bool UFXLibraryBPLibrary::ExportAssetThumbnail(UObject* Asset, const FString& OutputImagePath)
{
	if (!Asset)
	{
		return false;
	}

	// UE 5.4: use ThumbnailTools to read the already-cached thumbnail.
	const FObjectThumbnail* Thumbnail = ThumbnailTools::FindCachedThumbnail(Asset->GetFullName());
	if (!Thumbnail)
	{
		UE_LOG(LogTemp, Warning,
			TEXT("[FXLibrary] No cached thumbnail for '%s'. Open the asset once in the Content Browser to generate one, then retry."),
			*Asset->GetName());
		return false;
	}

	const TArray<uint8>& RawData = Thumbnail->GetUncompressedImageData();
	const int32 Width = Thumbnail->GetImageWidth();
	const int32 Height = Thumbnail->GetImageHeight();
	if (RawData.Num() == 0 || Width == 0 || Height == 0)
	{
		return false;
	}

	IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
	TSharedPtr<IImageWrapper> ImageWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
	if (!ImageWrapper.IsValid())
	{
		return false;
	}

	// FObjectThumbnail uncompressed data is BGRA8.
	if (!ImageWrapper->SetRaw(RawData.GetData(), RawData.Num(), Width, Height, ERGBFormat::BGRA, 8))
	{
		return false;
	}

	// UE 5.4: GetCompressed() returns TArray64<uint8>.
	TArray64<uint8> Compressed = ImageWrapper->GetCompressed();
	if (Compressed.Num() == 0)
	{
		return false;
	}

	return FFileHelper::SaveArrayToFile(Compressed, *OutputImagePath);
}
