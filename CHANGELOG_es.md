# Registro de cambios

Los cambios notables de py-slowdown. Las versiones publicadas, con la
AppImage, el paquete de Debian, el RPM, el wheel y el código fuente, están en
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) y
[GitHub](https://github.com/nivaca/py-slowdown/releases).

## Sin publicar

- **Una pausa vuelve adonde empezó a tocar**: Espacio, o el botón, pausa y
  lleva la posición de vuelta allí, para tocar otra vez el mismo pasaje
  desde el mismo lugar; la barra de estado dice dónde se pausó. Si se mueve
  mientras suena, vuelve al lugar nuevo; con una selección que se repite,
  dentro de ella; al final del archivo, también. Reproducción > Seguir
  desde la pausa (Mayús+Espacio) sigue desde donde se pausó, como hacía
  Espacio hasta ahora.
- **El volumen sube hasta 150 %**, para grabaciones hechas bajas; su valor
  aparece en por ciento junto a la barra, y por encima de 100 % la barra y
  el número están en rojo. Lo que pasa del máximo se recorta.
- **La altura en semitonos y cents**, cada uno con una perilla (el 0
  arriba) y su valor al lado: un paso por cada muesca de la rueda del
  ratón, y un doble clic la vuelve a 0. Los semitonos de −12 a +12, los cents (centésimas de semitono) de −50 a
  +50, para afinar una grabación con un instrumento; se suman. Ctrl+↑ y
  Ctrl+↓ mueven un semitono y conservan los cents; mover los cents nunca
  hace saltar los semitonos. El volumen pasa a la derecha de la primera
  fila, para dejar sitio.
- **Sin el botón Formantes**: conservar los formantes queda solo en el
  menú, Reproducción > Conservar los formantes (en gris, como lo estaba el
  botón, mientras la altura es la de la grabación). Las dos perillas de la
  altura quedan más juntas.
- **Cuenta previa > Golpes**: cuántos golpes da la cuenta previa (4 al
  principio), de una lista en el menú (de 1 a 8, 12, 16), el elegido
  marcado; el diálogo sigue aceptando cualquier número de 1 a 16.
- **Archivo > Guardar el .slx** (Ctrl+S) escribe el `.slx` de la grabación
  enseguida, sin cerrarla; con Archivos de ajustes en No se guardan, lo
  escribe igual junto a la grabación.
- **Los archivos de ajustes terminan en `.slx`**: `canción.slx` para
  `canción.mp3` (y `canción.flac.slx`, si `canción.slx` es de otro
  archivo), con XML dentro, como antes. Los `canción.xml` de 1.2.0 se leen
  todavía, y se borran cuando está escrito su `.slx`. Abrir un `.slx`
  (Archivo > Abrir, el administrador de archivos, o soltándolo en la
  ventana) abre su grabación, donde dice o, si se movió con él, a su lado.
  Los instaladores hacen de py-slowdown el programa de los `.slx`: en Linux,
  un tipo propio, `application/x-py-slowdown`, en el RPM, el paquete de
  Debian, el instalador de la AppImage e `install/install.sh`; en Windows,
  en el registro, como programa de los `.slx` solo si no había otro (los
  modelos de Simulink también terminan en `.slx`); en macOS, un tipo que la
  aplicación declara.
- **El primer pulso, un marcador propio**: Cuenta previa > El primer pulso
  está aquí (Mayús+C), o el clic derecho sobre la forma de onda, marca el
  primer pulso de la grabación con un marcador verde con un 1, en negrita
  en el panel, guardado con los demás marcadores (en `bookmarks.json` y en
  el `.slx`); así no se pierde cuando la posición se mueve o el archivo se
  cierra. Hay uno por archivo; Cuenta previa > Quitar el primer pulso lo
  quita. Con él, la grabación entra tras la cuenta en el pulso más cercano
  de la rejilla que forman el primer pulso y el tempo, empiece donde
  empiece; el desfase de la cuenta previa sobra entonces, y su diálogo lo
  muestra en gris. Si hay un primer pulso, el tempo de la cuenta se guarda
  con el archivo aunque esté apagada. Cuenta previa: el primer pulso en la
  posición sale del clic derecho (lo hace la entrada del menú).

## 1.2.0 — 2026-11-24

Los ajustes de cada grabación viajan con ella, en un archivo XML de su
nombre; velocidades propias en un botón; una calidad de reproducción a
elegir; y una ventana más clara: Oír y Cuenta previa en la barra de menús,
botones que muestran cuándo están encendidos.

- **Formantes solo con la altura movida**: el botón Formantes (y
  Reproducción > Conservar los formantes) está apagado mientras la altura
  es la de la grabación, donde no cambia nada; guarda su estado.
- **Los botones encendidos se ven encendidos**: Formantes y el botón de
  repetir, encendidos, se ven llenos del color de selección del tema (de
  gris, si están encendidos pero apagados), y no apenas hundidos.
- **Velocidades elegidas de antemano**: el botón Velocidades, junto a 1×, y
  Reproducción > Velocidades elegidas muestran velocidades en por ciento
  (al principio 50, 60, 70, 75, 80, 90, 100, 110, 125 y 150), con la que
  suena marcada; Cambiar las velocidades cambia la lista, Restaurar las de
  siempre la devuelve. El deslizador se queda.
- En cada menú, ya no hay dos acciones con la misma letra de Alt, en
  ninguno de los dos idiomas (Ir al final y Conservar los formantes la
  tenían; una prueba las revisa todas).
- **Los ajustes de cada grabación en un archivo XML de su nombre**: al
  cerrar un archivo, su posición, velocidad, altura, formantes, manera de
  oír, selección, cuenta previa, marcadores y bucles se escriben en
  `canción.xml` (para `canción.mp3`), con la ruta completa, el tamaño y la
  fecha de la grabación. Viaja con la grabación: si se mueven o se copian
  juntos, todo vuelve; al abrir un archivo, manda su XML. Si `canción.xml`
  es de otro archivo, es `canción.flac.xml`. Configuración > Archivos de
  ajustes de cada grabación: junto al archivo de audio (al principio), en
  una carpeta, o no se guardan.
- **Sin los botones Cuenta previa y Oír**: bastan sus menús; el botón
  Marcar se queda. Lo que hace ahora la cuenta previa lo dice la barra de
  estado, con el puntero sobre las acciones de su menú.
- **Oír y Cuenta previa tienen sus propios menús**, en la barra de menús,
  entre Reproducción y Marcadores: Oír tiene los canales y los filtros
  (como su botón), y Cuenta previa tiene Contar antes de tocar, Marcar el
  tempo y los ajustes de la cuenta previa, que ya no están en Reproducción
  ni en Configuración.
- **Calidad de la reproducción** (Configuración): la más alta, el motor R3
  de Rubber Band como hasta ahora; más liviana, R3 con una ventana corta,
  que necesita la mitad del procesador y tiene menos retraso, con algo
  menos de detalle en los graves; o el motor anterior, R2, de ataques
  nítidos, que algunos prefieren para la batería y la percusión. Cambia
  mientras suena, y se recuerda. Las exportaciones usan siempre la más
  alta.

## 1.1.0 — 2026-11-24

Para trabajar con la música: exportar lo que se oye, oír una parte de la
mezcla, guardar bucles y cada archivo como se tocó, cambiar las teclas; y
los archivos se leen mucho más rápido.

- **Toda la forma de onda enseguida, la segunda vez**: una vez leído un
  archivo, su forma de onda se guarda en la carpeta de caché (unos 4 MB por
  hora y media, de los 200 archivos abiertos más recientemente), y la vez
  siguiente toda la forma de onda y la duración exacta están apenas se
  abre, mientras el sonido se lee como antes. Un archivo que cambió se lee
  de nuevo.
- **Atajos de teclado propios**: Configuración > Atajos de teclado muestra
  cada acción con sus teclas; un clic en las teclas y las nuevas las
  cambian (un pedal de pie que manda teclas sirve igual). Unas teclas en
  dos acciones no se aceptan, Restaurar los de siempre los devuelve, y solo
  se guardan los cambiados. Ayuda > Atajos de teclado muestra las teclas
  como están. Las páginas de manual dicen Mayús+L y Ctrl+E.
- **Cada archivo como se tocó**: al cerrar un archivo, su velocidad, su
  altura, los formantes, la manera de oír, la selección (y si se repetía)
  y, con la cuenta previa encendida, el tempo y el desfase de la cuenta se
  guardan con sus marcadores, y vuelven al abrirlo de nuevo. Solo se guarda
  lo que no es lo de siempre; un archivo sin nada guardado los deja como
  están.
- **Bucles, selecciones guardadas con un nombre**: Reproducción > Guardar la
  selección como bucle (Mayús+L), o Guardar la selección en la pestaña
  nueva Bucles del panel (ahora Marcadores y bucles), guarda la selección,
  y su nombre se escribe en la lista. Un doble clic en sus tiempos la vuelve
  a elegir, la repite y va a su comienzo. Se guardan para cada archivo, con
  sus marcadores.
- **Exportar el audio**: Archivo > Exportar el audio (Ctrl+E) guarda el
  archivo entero, o la selección, como suena: a la velocidad y la altura
  elegidas, con los formantes si se conservan y, si se pide, como se oye
  (Oír). En WAV, FLAC, MP3 u Opus, con el nombre de la grabación, su
  velocidad y su altura. Se hace en segundo plano, con una barra de
  progreso y Cancelar, mientras la grabación sigue sonando (unas 13 veces
  más rápido que el tiempo real). El archivo entero a 1× es el archivo
  mismo, muestra por muestra; una selección entra y sale en una rampa
  corta; un filtro no lo atrasa.
- **Oír una parte de la mezcla**: Reproducción > Oír, y el botón Oír de la
  segunda fila, eligen los canales (los dos, solo el izquierdo o el
  derecho, los dos en uno, o la mezcla sin su centro, donde suelen estar la
  voz y el solo) y un filtro (solo los graves, debajo de 250 Hz, para
  seguir la línea del bajo, o todo menos los graves). Los filtros son de
  fase lineal y se aplican bloque tras bloque sin costuras; un cambio,
  mientras suena, pasa de uno a otro en un fundido. La elección se
  recuerda.
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
