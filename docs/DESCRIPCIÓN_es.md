# py-slowdown 1.0.0: descripción

## Análisis

py-slowdown es un reproductor de audio que toca una grabación más lenta o más rápida sin cambiarle la altura, la muestra como forma de onda y guarda marcadores en ella. Lo hizo Nicolas Vaughan en noviembre de 2026, para transcribir clases y entrevistas grabadas, donde hace falta oír un pasaje una y otra vez a una velocidad que se pueda seguir; también sirve para sacar música de oído.

Los requisitos fueron pocos. Debía abrir los archivos de audio corrientes (MP3, MP4, FLAC y los demás), mostrar la forma de onda, tener los mandos de cualquier reproductor (tocar, pausar, detener, ir al principio y al final, atrás y adelante), poner marcadores en la posición que suena y cambiar la velocidad mientras suena, con una calidad muy alta. Este último decidió casi todo lo demás. Como los otros programas de escritorio del autor, por ejemplo py-pdftools, tiene una ventana de Qt, una interfaz en inglés y en español y una configuración que se conserva de una sesión a otra.

## Diseño

El programa tiene pocos módulos, cada uno con un trabajo. `audio.py` abre y decodifica un archivo; `engine.py` produce el audio a la velocidad pedida y lo lleva a la tarjeta de sonido; `rubberband.py` es el enlace con la biblioteca Rubber Band; `bookmarks.py` guarda los marcadores y la posición de cada archivo; `waveform.py` dibuja la forma de onda; `panel.py` es la lista de marcadores; `window.py` es la ventana, con sus menús y atajos; `interface.py` traduce la interfaz; `timefmt.py` escribe y lee tiempos, y `app.py` arranca el programa.

El motor se divide en dos. `Renderer` hace el audio de salida por bloques, a partir de las muestras decodificadas y de una velocidad. `Player` lo lleva a la tarjeta: un hilo productor mantiene llena una cola corta (0,15 segundos) y la función que llama PortAudio solo copia de ella. Cada bloque lleva el cuadro del archivo donde empieza y cuántos cuadros del archivo vale cada cuadro de salida, de modo que la posición que se muestra es la que se oye, a cualquier velocidad.

La altura en semitonos la cambia Rubber Band en la misma pasada que la velocidad, con su opción para la altura que cambia mientras suena. Hubo dos decisiones de fondo. La primera: a 1× y a la altura de la grabación el archivo se copia tal cual, muestra por muestra, y Rubber Band solo se usa a otras velocidades, porque su motor R3 no es transparente a 1× (dejaba una diferencia de unos −40 dB en un sonido ruidoso). La segunda: las muestras decodificadas no van a la memoria sino a un archivo temporal sin nombre, mapeado en memoria; una clase de dos horas, en estéreo y en coma flotante de 32 bits, ocupa unos 2,5 GB, y así el sistema solo carga lo que se lee. Después de la 1.0.0 las muestras pasaron a guardarse en enteros de 16 bits (1,3 GB para esas dos horas), exactas para un archivo de 16 bits y, para los demás, sin pérdida audible.

Los marcadores y el punto donde se dejó cada archivo se guardan en un archivo JSON, por la ruta completa del archivo de audio, que no se modifica.

## Implementación

Está escrito en Python 3.14. Usa PyAV (o el programa ffmpeg) para leer los archivos, la biblioteca Rubber Band para el estiramiento, sounddevice para la tarjeta de sonido, PySide6 para la ventana y NumPy para las cuentas. Son 65 archivos y unas 11 100 líneas, 6800 de ellas en Python.

### El estiramiento

El estiramiento lo hace la biblioteca Rubber Band, de Breakfast Quay, con su motor R3 («finer»), en modo de tiempo real, llamada por su interfaz en C con un enlace propio hecho con ctypes (`rubberband.py`). La primera versión usaba pylibrb, que declara la GPL 2 sin «o posterior» y no se puede combinar con un programa bajo la GPL 3; Rubber Band sí, porque está bajo la GPL 2 «o posterior». Los métodos sencillos (WSOLA, un vocoder de fase) se escriben fácil en NumPy, pero suenan metálicos o borrosos lejos de 1×; Rubber Band es la referencia en este campo. Llamado desde Python por bloques de 1024 cuadros, R3 corre entre 15 y 24 veces más rápido que el tiempo real en el computador del autor. Para que la salida corresponda justo a un punto del archivo, el estirador recibe antes el audio que precede a ese punto (el relleno que pide al empezar) y se descartan los primeros cuadros de su salida, tantos como el retraso que anuncia.

### Lectura de los archivos

PyAV trae FFmpeg, de modo que lee casi cualquier formato, también el sonido de los videos. Donde PyAV no está (Fedora no lo empaqueta, así que el RPM no lo tiene), los archivos los lee el programa `ffmpeg` por una tubería, y `ffprobe` dice su duración. El remuestreador de FFmpeg convierte cada archivo a enteros de 16 bits, en mono o en estéreo (los demás canales se mezclan). La decodificación corre en un hilo propio: mientras sigue, la ventana dibuja y toca lo que ya está. Si un archivo dura más de lo que anuncia, el archivo temporal crece sin perder lo escrito. Al decodificar se calculan los picos de la forma de onda (el mínimo y el máximo de cada grupo de 256 cuadros); cuando la vista se acerca más que un grupo por píxel, se usan las muestras mismas.

### Cortes sin chasquidos

Cada corte (una pausa, un salto, el paso de la copia a Rubber Band o al revés) se suaviza con una rampa de unos milisegundos, que baja antes del corte y sube después. En los saltos, los pocos cuadros que se conservan para bajar a cero se atenúan en el momento mismo del salto, porque a veces sonaban antes de que el productor alcanzara a poner el bloque siguiente.

### La selección repetida y la cuenta previa

Una selección se repite sin pausa porque se repite donde se lee el archivo: el renderizador, y con él Rubber Band, reciben un solo flujo continuo, la selección una vez tras otra. En la unión, la última centésima de segundo de la selección se apaga mientras sube lo que precede a su principio (un fundido de igual potencia), así que no hay hueco ni chasquido, a ninguna velocidad. La cuenta previa son unos golpes que hace el programa (el primero más agudo), puestos al frente de la cola del sonido, antes de la grabación: es exacta a la muestra, y su tempo puede seguir la velocidad.

### Las bibliotecas de la AppImage

La AppImage debe correr en sistemas más viejos que el que la hace, y el Rubber Band y el PortAudio de Fedora piden la glibc 2.43 y la 2.38. `tools/build-libs.py` compila los dos de su código, comprobado por su SHA-256, con el compilador de zig para la glibc 2.28 y con la biblioteca de C++ dentro: Rubber Band en su versión de un solo archivo, con su FFT propia (corre de 12 a 19 veces más rápido que el tiempo real), y PortAudio solo con ALSA, que carga al correr y que PipeWire y PulseAudio atienden.

### La tarjeta de sonido

Se eligió sounddevice, y no QtMultimedia, porque su función de llamada corre en un hilo de PortAudio, fuera del bucle de eventos de Qt: el dibujo de la ventana no puede retrasarla. Si la tarjeta no acepta la frecuencia de muestreo del archivo, este se decodifica de nuevo a la de la tarjeta.

## Validación

Hay 115 pruebas automáticas (`tests/`), que `tools/test.py` corre a la vez, cada archivo en un proceso propio, en unos segundos. Leen los cinco tipos principales de archivo (WAV, FLAC, MP3, AAC y Opus), hechos por las propias pruebas, con PyAV y con el programa ffmpeg, y comprueban que las muestras decodificadas sean las escritas, también cuando un archivo dura más de lo que anuncia o está cortado. Comprueban que a 1× la salida sea el archivo mismo, muestra por muestra; que a seis velocidades, de 0,25× a 3×, la salida tenga la duración debida, conserve la altura (un tono de 220 Hz sigue en 220 Hz) y deje cada tictac de un archivo de prueba en su lugar, con menos de 20 milisegundos de error, y que un salto mientras suena no chasquee; que una selección se repita sin pausa, muestra por muestra a 1× y en su lugar al estirarla, que la cuenta previa suene antes de la grabación sin mover la posición, y que la altura suba o baje lo pedido (medida en la frecuencia de un tono) sin mover los tictacs. El reproductor se prueba con una tarjeta de sonido falsa que las pruebas mueven, y la ventana fuera de la pantalla: abrir un archivo, los mandos, la velocidad, los marcadores, el punto donde se dejó, un archivo que no es audio y la interfaz en español, cuyo archivo debe tener todos los textos del programa y ningún otro. Otras pruebas revisan el enlace con Rubber Band (también cuando falta la biblioteca) y el empaquetado: que las versiones coincidan, la licencia, el archivo .desktop, los metadatos de AppStream, el spec, las páginas de manual, los íconos, la clave y la firma de una versión, con una clave hecha para la prueba, y la documentación: que los manuales digan la versión del programa y tengan sus imágenes y sus PDF; y los instaladores: el .run se hace de una AppImage de mentira y se instala y desinstala en una carpeta personal de la prueba. Después de publicada la 0.1.0, el sonido se cortaba cada segundo: cada vez que la posición avanzaba un píxel, la forma de onda se redibujaba en más de 100 ms con el GIL tomado, y la función que alimenta la tarjeta no alcanzaba a correr; ahora se dibuja una vez y solo se copia, y una prueba lo vigila. Después de la 1.0.0, una onda a medio dibujar al abrir un archivo llevó a redibujarla mientras se lee, a lo sumo cinco veces por segundo, y a hacer sus imágenes con un mapa de bytes que Qt colorea: en una pantalla de 3800 píxeles tardan 2,7 ms en vez de 12, y leer un archivo de 30 minutos las rehace 13 veces y no unas 75. La lectura misma se midió también: menos de la mitad era decodificar, y el resto, guardar uno por uno en Python los trozos de 1152 cuadros del MP3; con FFmpeg dando ya enteros de 16 bits (sin una muestra distinta de las que daba el programa) y los trozos juntados en bloques de 32 768 cuadros, un archivo de 30 minutos se lee en 1,3 s y no 2,2 en MP3, y en 0,3 s y no 1,2 en FLAC. Además, el reproductor se probó en la tarjeta de sonido real, a siete velocidades, sin que se vaciara nunca la cola, también con el PortAudio y el Rubber Band compilados para la AppImage; se hicieron la AppImage (que arrancó con un archivo), el paquete de Debian y el RPM, y el instalador lo instaló y lo quitó en una carpeta personal temporal.

## Plataforma

Funciona en Linux, en Windows 10 y posteriores, y en macOS 13 y posteriores (Apple Silicon e Intel). Los instaladores de cada sistema llevan todo lo que el programa necesita, su propio Python incluido; los de Windows y macOS los hace y los prueba GitHub en sus propias máquinas, y a mano solo se ha probado en Fedora 45. Desde el código necesita Python 3.14 o posterior, la biblioteca Rubber Band (versión 3 o posterior) y, en Linux, PortAudio: `rubberband-libs` y `portaudio` en Fedora, `librubberband3` (o `librubberband2`) y `libportaudio2` en Debian y Ubuntu, `rubberband` en Homebrew. Los instaladores no están firmados por Microsoft ni por Apple, así que SmartScreen y Gatekeeper avisan la primera vez. No necesita internet.

### Licencias

py-slowdown es software libre, bajo la Licencia Pública General de GNU, versión 3 o posterior. Rubber Band está bajo la GPL 2 o posterior (su código se publica con cada versión, porque la AppImage y el paquete de Debian llevan una copia compilada), PyAV y NumPy bajo la licencia BSD, FFmpeg bajo la LGPL 2.1 o posterior, PySide6 bajo la LGPL 3, y sounddevice y PortAudio bajo la licencia MIT.

## Ambiente

Fue desarrollado en Fedora 45, con Python 3.14 y uv. El código está en GitHub (github.com/nivaca/py-slowdown), con una copia en Codeberg.

Cada versión trae un instalador para Windows (hecho con Inno Setup), dos imágenes de disco para macOS (Apple Silicon e Intel), un instalador para cualquier Linux (`.run`), un RPM para Fedora (también en Copr), una AppImage, un paquete de Debian, el wheel y el código, todos firmados con la clave del proyecto (`packaging/RPM-GPG-KEY-py-slowdown`), con `SHA256SUMS` firmado; `install/install.sh` lo instala desde el código en Linux y macOS. Desde el código se abre con `uv run py-slowdown [ARCHIVO]`; las pruebas, con `uv run python tools/test.py`, y la publicación de una versión se explica en `packaging/RELEASING.md`. La configuración (ventana, volumen, salto, idioma, archivos recientes) está en `~/.config/py-slowdown/py-slowdown.conf`; los marcadores y las posiciones, en `~/.local/share/py-slowdown/bookmarks.json`, y las muestras de un archivo abierto, en un archivo temporal sin nombre dentro de `~/.cache/py-slowdown/`, que desaparece al cerrarlo. El autor es Nicolas Vaughan (nicolasvaughan@proton.me).

### Los instaladores

`tools/bundle-installer.py` hace los de Windows y macOS, cada uno en su sistema (en GitHub, `.github/workflows/installers.yml`, que además los instala, los prueba con `packaging/installer/check.py` y los quita): un Python 3.14 de python-build-standalone, fijado con su SHA-256, con py-slowdown y sus paquetes dentro, Qt recortado y el Rubber Band de cada sistema (para Windows compilado con zig; para macOS, con el clang de Apple, porque usa allí la FFT de Accelerate). `tools/bundle-run.py` hace el `.run` de Linux con lo que trae la AppImage. La configuración, los marcadores y el caché van a las carpetas de cada sistema.

### Documentación

La documentación sigue la de py-pdftools, en inglés y en español: los README, los registros de cambios, estas dos descripciones, la lista del software de código abierto que usa, con sus versiones y licencias (`docs/THIRD-PARTY.md`, `docs/TERCEROS_es.md`), las páginas de manual y un manual de usuario en cada idioma (`docs/MANUAL_en.pdf`, `docs/MANUAL_es.pdf`, hechos con LuaLaTeX, con índice). Sus imágenes las hace `tools/manual_images.py`, con la ventana dibujada fuera de la pantalla sobre una grabación de muestra. Las imágenes en español mostraron que las palabras propias de Qt (Aceptar, Cancelar, los nombres de las teclas) seguían en inglés; ahora se cargan las traducciones de Qt.
