Unicode true
!define APP_NAME "OMNIX AI"
!define APP_VERSION "6.5"
!define APP_EXE "AICompanion.exe"
Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\..\..\..\outputs\OMNIX-AI-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\OMNIX AI"
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
  CreateDirectory "$SMPROGRAMS\OMNIX AI"
  CreateShortcut "$SMPROGRAMS\OMNIX AI\OMNIX AI.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$DESKTOP\OMNIX AI.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\OMNIX AI\OMNIX AI.lnk"
  RMDir "$SMPROGRAMS\OMNIX AI"
  Delete "$DESKTOP\OMNIX AI.lnk"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd


