Unicode true
!define APP_NAME "AI Assistant"
!define APP_VERSION "6.5"
!define APP_EXE "AICompanion.exe"
Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\..\..\..\outputs\AICompanion-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\AI Assistant"
RequestExecutionLevel user
SetCompressor /SOLID zlib
Icon "..\config\ai_companion.ico"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "/oname=${APP_EXE}" "..\..\..\..\outputs\AICompanion.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\AI Assistant"
  CreateShortcut "$SMPROGRAMS\AI Assistant\AI Assistant.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$DESKTOP\AI Assistant.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\AI Assistant\AI Assistant.lnk"
  RMDir "$SMPROGRAMS\AI Assistant"
  Delete "$DESKTOP\AI Assistant.lnk"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd


