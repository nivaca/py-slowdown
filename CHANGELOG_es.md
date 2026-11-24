# Registro de cambios

Los cambios notables de py-slowdown. Las versiones publicadas, con la
AppImage, el paquete de Debian, el RPM, el wheel y el código fuente, están en
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) y
[GitHub](https://github.com/nivaca/py-slowdown/releases).

## Sin publicar

- **Conservar los formantes**: el botón Formantes, junto a la altura, y
  Reproducción > Conservar los formantes hacen que Rubber Band conserve los
  formantes cuando la altura se mueve, de modo que una voz o un instrumento
  conserva su timbre natural en vez de sonar más pequeño (más agudo) o más
  grande (más grave). Se cambia mientras suena, y se recuerda.
- **La forma de onda llena la ventana al abrir un archivo**: se dibujaba
  mientras el archivo todavía se leía, y a veces se quedaba así, a medias o
  a la escala de la duración que el archivo anunciaba, hasta que otra cosa
  (un clic, cambiar el tamaño de la ventana) la volviera a dibujar. Ahora
  se redibuja a medida que el archivo se lee, y con su duración real cuando
  termina de leerse.
- **Una forma de onda más liviana**: mientras se lee un archivo se
  redibuja a lo sumo cinco veces por segundo; mover la posición ya no
  rehace sus imágenes durante la lectura, y Qt las hace de un solo mapa de
  bytes, más del doble de rápido (2,7 ms en vez de 12 en una pantalla de
  3800 píxeles).
- **La mitad del espacio para las muestras decodificadas**: se guardan en 16
  bits, no en coma flotante de 32 (1,3 GB para dos horas en estéreo, no
  2,5 GB). Un archivo de 16 bits se guarda muestra por muestra; lo que pase
  del máximo se recorta.
- **Los archivos se abren más rápido**: FFmpeg da ya las muestras en 16
  bits, se guardan en bloques y no en trozos de mil cuadros, y PyAV
  decodifica en varios hilos donde el códec lo permite. Un archivo de 30
  minutos se lee en 1,3 s y no en 2,2 si es MP3, y en 0,3 s y no en 1,2 si
  es FLAC.
- **Los archivos largos se leen en cuatro partes a la vez**: un archivo de
  cuatro minutos o más en MP3, FLAC, Ogg Vorbis u Opus se lee por partes,
  cada una en un proceso propio, y cada parte se une a la anterior solo
  donde un segundo de ambas coincide muestra por muestra; si no, el archivo
  se lee de corrido. El resultado es siempre el de una lectura seguida. Un MP3
  de 98 minutos se lee en 3,1 s y no en 7,5. El AAC, y un
  archivo tocado a otra frecuencia que la suya, se leen de corrido.

## 1.0.0 — 2026-11-24

La primera versión estable.

- **La altura, en semitonos**: de 12 abajo a 12 arriba, de uno en uno o en
  décimas (para afinar con un instrumento una grabación desafinada), sin
  cambiar la velocidad, y mientras suena, sin chasquidos (la opción de
  Rubber Band para la altura que cambia mientras suena). La casilla Altura,
  junto a la velocidad; Ctrl+↑ y Ctrl+↓; Mayús+N, o el botón 0, para la
  altura original. Medido, un tono queda a menos de un centésimo de
  semitono de la altura pedida.
- **La cuenta previa se oye en los auriculares Bluetooth**: muchos se
  silencian mientras reciben silencio y despiertan tarde para un golpe
  corto, así que se tragaban la cuenta. Ahora empieza con un soplo muy
  tenue, 0,4 s antes del primer golpe, y lo mantiene entre los golpes; los
  golpes son más llenos (60 ms, una nota y su octava). El pulso aparece en
  la forma de onda con el primer golpe.
- **El desfase de la grabación después de la cuenta previa**: cuando el
  primer pulso de la grabación no está justo en la posición, Desfase de la
  grabación, en el diálogo de la cuenta previa, la hace entrar antes
  (negativo) o después (positivo), hasta 2 segundos de la grabación, para
  que entre en el pulso a cualquier velocidad; antes, solo hasta el último
  golpe, que no se corta.
- **Reabrir el último archivo al empezar** (Configuración): el programa
  vuelve a abrir el último archivo, donde se dejó, salvo que se nombre otro
  en la línea de órdenes. Al principio, desactivado.
- **El primer pulso sobre la forma de onda**: un clic derecho sobre el
  primer pulso de la grabación, Cuenta previa: el primer pulso está aquí,
  fija el desfase de la posición a él (y activa la cuenta previa); una línea
  verde con un 1 muestra dónde lo espera la cuenta.
- **Marcar el tempo**: el botón Marcar, junto a Cuenta previa, o la tecla T,
  pulsados con el pulso mientras suena la música, miden su tempo (el valor
  del medio de los intervalos entre los ocho últimos golpes; una pausa de
  más de dos segundos empieza otra vez), que pasa a ser el de la cuenta
  previa; a otra velocidad, con la cuenta siguiéndola, se guarda el tempo
  de la grabación. El diálogo de la cuenta previa también tiene un botón
  Marcar.
- **Los ajustes de la cuenta previa se encuentran fácil**: una flecha junto
  al botón Cuenta previa los abre, y también Configuración > Cuenta previa
  (además de Reproducción > Ajustes de la cuenta previa); la etiqueta del
  botón dice cuáles son.
- Los mandos están en dos filas, la velocidad, la altura y el volumen debajo
  de los demás: en una sola, la ventana no cabía en una pantalla de 1366
  píxeles.

## 0.2.0 — 2026-11-24

- **Instaladores para Windows y macOS**, que llevan su propio Python, Qt,
  FFmpeg y Rubber Band: para Windows 10 y posteriores, un instalador hecho
  con Inno Setup, solo para el usuario (sin permisos de administrador) o
  para todos, con su entrada en el menú Inicio y py-slowdown en «Abrir con»
  para los archivos de audio; para macOS 13 y posteriores, una imagen de
  disco con py-slowdown.app, para Apple Silicon y para Intel. GitHub los
  hace, los prueba y los quita, en sus propias máquinas, y se firman como
  los demás archivos.
- **Un instalador para cualquier Linux** (`.run`), hecho de la AppImage:
  para el usuario o, con sudo, para todos, con la orden, la entrada del
  menú, los íconos, las páginas de manual y un desinstalador.
- **El sonido ya no se corta mientras suena** (en la 0.1.0, más o menos una
  vez por segundo en un archivo largo): cada vez que la posición avanzaba un
  píxel, la forma de onda se dibujaba otra vez, lo que tardaba más de 100 ms
  e impedía que el sonido llegara a la tarjeta. Ahora se dibuja una vez, y
  al moverse la posición solo se copia; la tarjeta tiene además un búfer
  mayor (0,1 s).
- **Repetir una selección, sin pausa**: Mayús+arrastrar sobre la forma de
  onda, I y O en la posición, o «Seleccionar de aquí al marcador
  siguiente»; luego Reproducción > Repetir la selección (L), o su botón. El
  final de la selección se funde en una centésima de segundo con lo que
  precede a su principio, antes del estiramiento, de modo que el pasaje
  suena como un solo flujo a cualquier velocidad.
- **Cuenta previa antes de tocar** (Reproducción > Contar antes de tocar,
  C, o su botón): de 1 a 16 golpes a 20–300 BPM, el primero más agudo, y
  luego la grabación; el tempo puede seguir la velocidad (120 BPM a 0,5× se
  cuentan a 60); la forma de onda muestra el pulso en grande.
- **Los archivos que se abren desde el Finder** (Abrir con, o soltados sobre
  el ícono del Dock) los abre la ventana.
- **Los marcadores y el sonido decodificado, en las carpetas de cada
  sistema**: `%APPDATA%` y `%LOCALAPPDATA%` en Windows, `~/Library` en macOS
  (en Linux, como antes).
- Los manuales y los README explican cómo instalarlo en cada sistema, y qué
  hacer cuando Windows o macOS avisan que el programa no está firmado por
  ellos.

## 0.1.0 — 2026-11-24

La primera versión.

- **Abre archivos de audio y el sonido de los videos**: MP3, M4A/AAC, MP4,
  FLAC, WAV, AIFF, Ogg, Opus, WMA y lo demás que lea FFmpeg, mediante
  PyAV, o con el programa ffmpeg donde PyAV no está (como en Fedora). Se
  leen en segundo plano a un archivo temporal mapeado en memoria, de modo
  que una grabación larga se puede tocar mientras todavía se lee.
- **Una forma de onda** con una regla de tiempos, lo ya tocado en otro
  color, los marcadores, acercar y alejar alrededor del puntero
  (Ctrl+rueda) y una barra de desplazamiento; un clic o un arrastre mueven
  la posición.
- **Los mandos de siempre**: tocar, pausar, detener, al principio, al
  final, atrás y adelante una longitud de salto (de 1 a 60 s; con el botón
  apretado siguen), un segundo atrás o adelante, y el volumen.
- **La velocidad de 0,25× a 3×**, que se cambia mientras suena, sin cambiar
  la altura, con el motor R3 de la biblioteca Rubber Band; a 1× el archivo
  suena tal cual, muestra por muestra.
- **Marcadores** con nombre, sobre la forma de onda y en un panel lateral;
  anterior y siguiente; se exportan como texto. Se guardan por archivo,
  con el punto donde se dejó, y sigue desde allí.
- **Una interfaz en inglés y en español**, también las palabras propias de
  Qt.
- **Paquetes**: un RPM firmado (también en Copr), una AppImage y un paquete
  de Debian que llevan su propio Rubber Band y su propio PortAudio, el
  wheel, el código y un ZIP, todos los archivos firmados, con SHA256SUMS;
  un instalador para Linux y macOS; páginas de manual y manuales de
  usuario (PDF) en inglés y en español.
