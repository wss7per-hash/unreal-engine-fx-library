#include "FXLibraryModule.h"
#include "FXLibraryBPLibrary.h"

#include "LevelEditor.h"
#include "Textures/SlateIcon.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "Framework/MultiBox/MultiBoxExtender.h"
#include "Widgets/SWindow.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Framework/Application/SlateApplication.h"
#include "Editor.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/MessageDialog.h"

DEFINE_LOG_CATEGORY_STATIC(LogFXLibrary, Log, All);

void FFXLibraryModule::StartupModule()
{
	// Extend the main editor menu bar with a "FX Library" pull-down.
	FLevelEditorModule& LevelEditorModule = FModuleManager::LoadModuleChecked<FLevelEditorModule>(TEXT("LevelEditor"));

	MenuExtender = MakeShared<FExtender>();
	MenuExtender->AddMenuBarExtension(
		"Help",
		EExtensionHook::After,
		nullptr,
		FMenuBarExtensionDelegate::CreateRaw(this, &FFXLibraryModule::AddMenu));

	LevelEditorModule.GetMenuExtensibilityManager()->AddExtender(MenuExtender);
}

void FFXLibraryModule::ShutdownModule()
{
	if (MenuExtender.IsValid())
	{
		if (FModuleManager::Get().IsModuleLoaded(TEXT("LevelEditor")))
		{
			FLevelEditorModule& LevelEditorModule = FModuleManager::GetModuleChecked<FLevelEditorModule>(TEXT("LevelEditor"));
			LevelEditorModule.GetMenuExtensibilityManager()->RemoveExtender(MenuExtender);
		}
		MenuExtender.Reset();
	}
}

void FFXLibraryModule::AddMenu(FMenuBarBuilder& MenuBarBuilder)
{
	MenuBarBuilder.AddPullDownMenu(
		FText::FromString("FX Library"),
		FText::FromString("FX Library Manager"),
		FNewMenuDelegate::CreateRaw(this, &FFXLibraryModule::FillMenu),
		"FXLibraryMenu");
}

void FFXLibraryModule::FillMenu(FMenuBuilder& MenuBuilder)
{
	MenuBuilder.AddMenuEntry(
		FText::FromString("Open FX Library Window"),
		FText::FromString("Open the FX Library panel"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FFXLibraryModule::OpenWindow)));

	MenuBuilder.AddSeparator();

	MenuBuilder.AddMenuEntry(
		FText::FromString("Export Selected -> .fxpack"),
		FText::FromString("Pack the selected Niagara/Cascade asset and its dependencies"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FFXLibraryModule::RunScript, FString(TEXT("fx_export.py")))));

	MenuBuilder.AddMenuEntry(
		FText::FromString("Import .fxpack"),
		FText::FromString("Unpack and import an .fxpack into this project"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FFXLibraryModule::RunScript, FString(TEXT("fx_import.py")))));

	MenuBuilder.AddMenuEntry(
		FText::FromString("Generate Thumbnails (Selected)"),
		FText::FromString("Export engine thumbnails for the selected assets"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FFXLibraryModule::RunScript, FString(TEXT("fx_thumbnail.py")))));

	MenuBuilder.AddMenuEntry(
		FText::FromString("List All FX Assets"),
		FText::FromString("Print all Niagara/Cascade assets to the Output Log"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FFXLibraryModule::RunScript, FString(TEXT("fx_list.py")))));
}

void FFXLibraryModule::OpenWindow()
{
	TSharedRef<SWindow> Window = SNew(SWindow)
		.Title(FText::FromString("FX Library Manager"))
		.ClientSize(FVector2D(340, 300))
		.SupportsMinimize(false)
		.SupportsMaximize(false);

	Window->SetContent(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().Padding(8).AutoHeight()
		[
			SNew(STextBlock).Text(FText::FromString("Select an asset in Content Browser,\nthen use a button below."))
		]
		+ SVerticalBox::Slot().Padding(6).AutoHeight()
		[
			SNew(SButton).Text(FText::FromString("Export Selected -> .fxpack"))
			.OnClicked_Raw(this, &FFXLibraryModule::OnExportClicked)
		]
		+ SVerticalBox::Slot().Padding(6).AutoHeight()
		[
			SNew(SButton).Text(FText::FromString("Import .fxpack"))
			.OnClicked_Raw(this, &FFXLibraryModule::OnImportClicked)
		]
		+ SVerticalBox::Slot().Padding(6).AutoHeight()
		[
			SNew(SButton).Text(FText::FromString("Generate Thumbnails (Selected)"))
			.OnClicked_Raw(this, &FFXLibraryModule::OnThumbClicked)
		]
		+ SVerticalBox::Slot().Padding(6).AutoHeight()
		[
			SNew(SButton).Text(FText::FromString("List All FX Assets"))
			.OnClicked_Raw(this, &FFXLibraryModule::OnListClicked)
		]);

	FSlateApplication::Get().AddWindow(Window);
}

FReply FFXLibraryModule::OnExportClicked() { RunScript(TEXT("fx_export.py")); return FReply::Handled(); }
FReply FFXLibraryModule::OnImportClicked() { RunScript(TEXT("fx_import.py")); return FReply::Handled(); }
FReply FFXLibraryModule::OnThumbClicked()  { RunScript(TEXT("fx_thumbnail.py")); return FReply::Handled(); }
FReply FFXLibraryModule::OnListClicked()   { RunScript(TEXT("fx_list.py")); return FReply::Handled(); }

void FFXLibraryModule::RunScript(FString ScriptName)
{
	TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("FXLibrary"));
	if (!Plugin.IsValid())
	{
		FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(TEXT("FXLibrary plugin not found.")));
		return;
	}

	const FString ScriptPath = FPaths::Combine(Plugin->GetContentDir(), TEXT("Python"), TEXT("FXLibrary"), ScriptName);
	if (!FPaths::FileExists(ScriptPath))
	{
		FMessageDialog::Open(EAppMsgType::Ok,
			FText::FromString(FString::Printf(TEXT("Script not found:\n%s"), *ScriptPath)));
		return;
	}

	// The PythonScriptPlugin provides the "py" console command to run a file.
	const FString Command = FString::Printf(TEXT("py \"%s\""), *ScriptPath);
	if (GEditor && GEditor->Exec(nullptr, *Command))
	{
		UE_LOG(LogFXLibrary, Log, TEXT("[FXLibrary] Ran script: %s"), *ScriptName);
	}
}

IMPLEMENT_MODULE(FFXLibraryModule, FXLibrary)
