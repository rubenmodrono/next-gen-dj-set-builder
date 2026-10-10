#!/usr/bin/env bash
# Creates a fresh Expo project (so it always matches the current Expo Go version),
# installs the 4 libraries this app needs and copies the app code into it.
set -euo pipefail
NAME="${1:-set-planifier}"
HERE="$(cd "$(dirname "$0")" && pwd)"
npx create-expo-app@latest "$NAME" --template blank-typescript --no-install
cd "$NAME"
npm install
npm install react-native-svg@^15.15.4 expo-clipboard@~57.0.2 expo-secure-store@~57.0.4 expo-audio@~57.0.5 @react-native-async-storage/async-storage@^2.2.0
node -e "const f=require('fs');const a=JSON.parse(f.readFileSync('app.json'));a.expo.userInterfaceStyle='dark';f.writeFileSync('app.json',JSON.stringify(a,null,2))"
cp "$HERE/App.tsx" ./App.tsx
rm -rf ./src && cp -R "$HERE/src" ./src
echo
echo "Listo. Ahora ejecuta:  cd $NAME && npx expo start"
echo "Abre Expo Go en el iPhone y escanea el QR (iPhone y ordenador en la misma red Wi-Fi)."
