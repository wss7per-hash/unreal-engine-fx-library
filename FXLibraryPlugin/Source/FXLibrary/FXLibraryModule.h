#pragma once

#include "Modules/ModuleManager.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "Framework/Commands/UIAction.h"

class FFXLibraryModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	// Main-menu extension
	void AddMenu(FMenuBarBuilder& MenuBarBuilder);
	void FillMenu(FMenuBuilder& MenuBuilder);

	// Floating panel
	void OpenWindow();
	FReply OnExportClicked();
	FReply OnImportClicked();
	FReply OnThumbClicked();
	FReply OnListClicked();

	// Run a Python script shipped in the plugin's Content/Python/FXLibrary folder
	void RunScript(FString ScriptName);

	TSharedPtr<FExtender> MenuExtender;
};
