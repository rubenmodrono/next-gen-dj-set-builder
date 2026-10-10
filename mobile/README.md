# Set Planifier (iPhone, Expo Go)

Crea una playlist de DJ para un género y una duración, siguiendo una curva de BPM y energía por tramos.
Cada tema sale como `Artista - Título (Mix) - 124 BPM - 8A (Am)`.

Los temas, el BPM y la tonalidad vienen de la lista Top 100 de Beatport del género elegido, así que el género es el real.
La app ordena los temas con la rueda Camelot y la curva (Warm-up 25 %, Peak time 50 %, Closing 25 %).

## Probarla en el iPhone

Necesitas Node 20 o superior en tu ordenador y la app **Expo Go** (App Store) en el iPhone.
El iPhone y el ordenador deben estar en la misma red Wi-Fi.

macOS o Linux:

    ./setup.sh set-planifier
    cd set-planifier
    npx expo start

Windows (PowerShell), desde esta carpeta:

    # Estando en la carpeta que contiene App.tsx y src:
    npx create-expo-app@latest sp-app --template blank-typescript --no-install
    cd sp-app
    npm install
    npm install react-native-svg@^15.15.4 expo-clipboard@~57.0.2 expo-secure-store@~57.0.4 expo-audio@~57.0.5 @react-native-async-storage/async-storage@^2.2.0
    Copy-Item ..\App.tsx .\App.tsx -Force
    Copy-Item ..\src .\src -Recurse -Force
    $a = Get-Content app.json -Raw | ConvertFrom-Json; $a.expo | Add-Member -NotePropertyName userInterfaceStyle -NotePropertyValue dark -Force; $a | ConvertTo-Json -Depth 10 | Set-Content app.json
    npx expo start

Nota: con npm 12, `create-expo-app` falla con `EALLOWSCRIPTS` si instala por su cuenta. Por eso se usa `--no-install` y luego `npm install`.

Escanea el QR con la cámara del iPhone y se abre en Expo Go.
Si no conecta por la red, usa `npx expo start --tunnel`.

El script crea un proyecto Expo nuevo en lugar de incluir uno, para que siempre coincida con la versión actual de Expo Go.

## Cómo obtiene los datos

1. Descarga la página de la lista de Beatport del género y lee los temas que lleva incrustados. No necesita ninguna clave.
2. Si Beatport cambia su página o bloquea la petición, y has activado un modelo en Ajustes, Gemini (capa gratuita, clave en aistudio.google.com) o Claude (clave en console.anthropic.com) lee la lista por ti.
3. Descarta los datos dudosos: BPM fuera del rango del género (por ejemplo 78 BPM en una lista de 120-130), temas sin tonalidad, varias versiones del mismo tema y más de 2 temas del mismo artista.

La lista se guarda 6 horas en el teléfono. El botón Actualizar lista la vuelve a pedir.

## Escuchar cada tema

Cada tema tiene un botón **Escuchar**. Busca el preview en este orden:
1. El preview que Beatport lista para ese tema en su página (el mismo audio y la misma versión que en beatport.com), si la página lo incluye.
2. Deezer (30 s).
3. Apple Music / iTunes (30 s).

Solo se reproduce un preview si el artista y el título coinciden con el tema. Si ninguna fuente lo tiene, el botón dice "Sin preview disponible" y no suena nada.
El audio suena aunque el iPhone esté en silencio.

## Límites que conviene conocer

- Los previews de Beatport son su contenido: úsalos solo para escuchar mientras preparas tus sets. Deezer e iTunes ofrecen API pública para previews.
- No se pudo medir la cobertura de Deezer e iTunes para tus géneros desde el entorno donde se escribió la app.

- La energía no existe en Beatport. Se estima a partir del BPM dentro de tu curva.
- Una sola lista Top 100 tiene unos 85 temas utilizables, y se concentran en un rango estrecho de BPM. Los sets muy largos repiten el estilo.
- Beatport no ofrece una API pública y sus condiciones pueden limitar el acceso automatizado. Úsalo para tu propia preparación de sets.
- No se ha podido ejecutar en un iPhone desde el entorno donde se escribió. Se comprobó el tipado contra Expo SDK 57, el empaquetado para iOS y las pruebas del motor con la lista real de Progressive House (carpeta `out`).

## Pruebas

    npx tsx tests/core.test.ts
    npx tsx scripts/realTest.ts 60 energy_boost

> Nota: con npm 12 no uses `npx expo install`: llama a npm con `--allow-scripts` y falla con `EALLOWSCRIPTS`. Por eso las dependencias nativas se instalan con `npm install` y versiones fijadas para SDK 57.
