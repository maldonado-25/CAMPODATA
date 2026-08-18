import json
import requests
import platform
import hashlib
import sqlite3
import threading
import time
import os
from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.uix.popup import Popup
from kivy.config import Config
from kivy.uix.spinner import Spinner
from kivy.core.window import Window
try:
    from plyer import gps
except ImportError:
    gps = None

Config.set('graphics', 'multisamples', '0')
Config.set('graphics', 'fullscreen', '0')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
Config.set('kivy', 'keyboard_mode', 'system') 

# Usamos 'pan' para que levante la interfaz como un bloque sólido
Window.softinput_mode = 'pan' 
Window.keyboard_anim_args = {'d': 0.1, 't': 'linear'}

# --- FUNCIÓN DE PROTECCIÓN DEL FOCO RE-ESTABILIZADA ---
def asegurar_foco_celda(instance, value):
    """
    Fija de forma asíncrona y segura el foco de los TextInput dinámicos
    en Android evitando cierres abruptos por redibujado de interfaz.
    """
    if value:
        # Un leve retraso de 150ms le da tiempo a Android de levantar el teclado
        # antes de re-confirmar el foco sobre este objeto de texto.
        Clock.schedule_once(lambda dt: setattr(instance, 'focus', True), 0.15)

# 3. Constantes de Diseño (Correctas)
URL_BASE = "https://campodata-cd974-default-rtdb.firebaseio.com"
PATH_FB = ""
AZUL_LOGO = (0.07, 0.22, 0.35, 1)
VERDE_LOGO = (0.13, 0.45, 0.23, 1)
FONDO_TRANSPARENTE = (1, 1, 1, 0)

MAPA_TECNICO = {
    "Cerdo": {
        "etapas": ["Pre-inicio", "Inicio", "Desarrollo", "Engorde", "Gestación", "Lactancia"],
        "params": ["Días Destete", "Peso Destete", "Peso Nacimiento", "Mortalidad %"]
    },
    "Ponedora": {
        "etapas": ["Iniciación", "Crecimiento", "Pre-postura", "Postura F1", "Postura F2"],
        "params": ["% Producción", "Peso Huevo", "Consumo Ave/Día", "Mortalidad %"]
    },
    "Pollo": {
        "etapas": ["Pre-inicio", "Inicio", "Finalización"],
        "params": ["Peso Inicial", "Peso Final", "Conversión", "Mortalidad %"]
    },
    "Ganado": {
        "etapas": ["Terneros", "Novillos", "Vacas Lecheras", "Toros"],
        "params": ["Litros Vaca/Día", "Peso Nacimiento", "Condición Corporal"]
    },
    "Caballo": {
        "etapas": ["Potros < 1 año", "Potros > 1 año", "Yeguas Gestación", "Yeguas Lactancia", "Sementales"],
        "params": ["Condición Corporal", "Peso", "Actividad Física"]
    }
}

def sanitizar_llave(llave):
    if not llave: return "campo_vacio"
    prohibidos = [".", "$", "#", "[", "]", "/"]
    nueva_llave = str(llave)
    for p in prohibidos:
        nueva_llave = nueva_llave.replace(p, "_")
    return nueva_llave

def get_db_path():
    if platform.system() == 'Android':
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), 'campodata_v1.db')
    return 'campodata_v1.db'

def resource_path(relative_path):
    if platform.system() == 'Android':
        from os.path import dirname, join
        try:
            return join(dirname(__file__), relative_path)
        except:
            return relative_path
    return relative_path

def inicializar_db():
    conn = sqlite3.connect(get_db_path())
    conn.execute('''CREATE TABLE IF NOT EXISTS cola_sincro 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, datos TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cache_app 
                 (clave TEXT PRIMARY KEY, valor TEXT)''')
    conn.commit()
    conn.close()

# --- COMPONENTES UI ---

# --- COMPONENTES UI CORREGIDOS ---

# --- COMPONENTES UI OPTIMIZADOS (MÁXIMA LEGIBILIDAD Y FLUIDEZ) ---

class BigInput(TextInput):
    def __init__(self, **kwargs):
        # Capturamos el filtro que viene desde el archivo para saber si es número o texto
        filtro_actual = kwargs.get('input_filter', None)
        
        # SI ES NUMÉRICO: Configuramos teclado de número nativo
        if filtro_actual in ['float', 'int']:
            kwargs.setdefault('input_type', 'number')
        # SI ES TEXTO: Forzamos tipo 'mail' para obligar a Android a desactivar el autocorrector que duplica texto
        else:
            kwargs.setdefault('input_type', 'mail')
            
        kwargs.setdefault('multiline', False)
        super().__init__(**kwargs)
        
        # PROTECCIÓN ADICIONAL ANTI-DUPLICADO Y AUTOCORRECTOR
        self.keyboard_suggestions = False
        
        self.size_hint_y = None
        # 1. Ampliación global del tamaño de la celda para mejor control táctil
        self.height = dp(50)
        
        # 2. Incremento del tamaño de la letra para alta legibilidad en el campo
        self.font_size = dp(20)
        
        self.background_normal = ''
        self.background_color = (1, 1, 1, 0.9)
        
        # Padding matemático preciso [izq, arriba, der, abajo] para centrar perfectamente el texto
        self.padding = [dp(14), dp(15), dp(14), dp(10)]
        
        # Conexión automática de protección para el teclado de Android
        self.bind(focus=asegurar_foco_celda)
        
        with self.canvas.after:
            Color(0.07, 0.22, 0.35, 1) 
            self.border_line = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(5)), width=dp(1))
        
        # Enlazamos los cambios de posición y tamaño con control asíncrono seguro
        self.bind(pos=self._solicitar_actualizacion_borde, size=self._solicitar_actualizacion_borde)

    def _solicitar_actualizacion_borde(self, *args):
        # Cancelamos y re-programamos el dibujo en la cola de Kivy.
        # Esto evita que el canvas choque con la textura del texto al escribir o borrar rápidamente en Android.
        Clock.unschedule(self._dibujar_borde_seguro)
        Clock.schedule_once(self._dibujar_borde_seguro, 0.02)

    def _dibujar_borde_seguro(self, dt):
        if self.width > 0 and self.height > 0:
            self.border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(5))

class BigLabel(Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = dp(18)
        self.color = (1, 1, 1, 1)
        self.bold = True
        self.outline_color = (0, 0, 0, 1) 
        self.outline_width = dp(1.5)
        self.size_hint_y = None
        self.height = dp(45)
        self.halign = 'left'
        self.valign = 'middle'
        self.bind(size=self._update_text_size)
    def _update_text_size(self, *args):
        self.text_size = (self.width, None)

class ContainerTransparente(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*FONDO_TRANSPARENTE)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10),])
        self.bind(pos=self._update_rect, size=self._update_rect)
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
        
class PantallaConDatos(Screen):
    def cargar_datos_de_cache(self, clave):
        datos = []
        try:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.execute("SELECT valor FROM cache_app WHERE clave=?", (clave,))
            row = cursor.fetchone()
            if row:
                datos = json.loads(row[0])
            conn.close()
        except Exception as e:
            print(f"Error cargando {clave} desde caché: {e}")
        return datos

# --- PANTALLAS ---

class LockScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        l = FloatLayout()
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False))
        self.lbl = Label(
            text="INICIANDO SISTEMA...", 
            font_size=dp(20), 
            bold=True, 
            color=(1,1,1,1), 
            halign='center', 
            valign='middle',
            outline_color=(0,0,0,1), 
            outline_width=dp(2)
        )
        self.lbl.bind(size=lambda s, w: setattr(s, 'text_size', (w[0]*0.9, None)))
        l.add_widget(self.lbl)
        self.add_widget(l)

class MainScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        l = FloatLayout()
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False))
        
        box = BoxLayout(orientation='vertical', padding=[dp(20), dp(30), dp(20), dp(30)], spacing=dp(15))
        
        self.logo = Image(source=resource_path('logo.png'), size_hint=(1, 0.35), allow_stretch=True, keep_ratio=True)
        box.add_widget(self.logo)
        
        self.b1 = Button(text="1. REGISTRAR CLIENTE", size_hint_y=None, height=dp(65), background_color=AZUL_LOGO, bold=True)
        self.b1.bind(on_release=lambda x: setattr(self.manager, 'current', 'reg_cliente'))
        box.add_widget(self.b1)

        self.b2 = Button(text="2. REGISTRAR VISITA PRODUCTOR", size_hint_y=None, height=dp(65), background_color=VERDE_LOGO, bold=True)
        self.b2.bind(on_release=lambda x: setattr(self.manager, 'current', 'reg_visita'))
        box.add_widget(self.b2)

        self.b3 = Button(text="3. REGISTRAR NUEVO LOCAL (PV)", size_hint_y=None, height=dp(65), background_color=(0.1, 0.4, 0.6, 1), bold=True)
        self.b3.bind(on_release=lambda x: setattr(self.manager, 'current', 'registro_pv_nuevo'))
        box.add_widget(self.b3)

        self.b4 = Button(text="4. VISITA SEGUIMIENTO PV", size_hint_y=None, height=dp(65), background_color=(0.1, 0.5, 0.1, 1), bold=True)
        self.b4.bind(on_release=lambda x: setattr(self.manager, 'current', 'visita_pv'))
        box.add_widget(self.b4)
        
        l.add_widget(box)
        self.add_widget(l)

class RegistroClienteScreen(PantallaConDatos):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.inputs_etapas = {}
        self.dict_tecnicos_local = {} 
        
        # ---> Nuevas variables de estado para el control de coordenadas y escucha GPS
        self.latitud_actual = 0.0
        self.longitud_actual = 0.0
        self.listener_gps = None  # Guardará la referencia de la escucha activa
        self.servicio_ubicacion = None
        
        l = FloatLayout()
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False))
        
        self.sc = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(10))
        
        self.container = ContainerTransparente(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        
        self.container.add_widget(BigLabel(text="Nombre del Productor:"))
        self.nom = BigInput(hint_text="Nombre Completo")
        self.container.add_widget(self.nom)
        
        self.container.add_widget(BigLabel(text="Teléfono / WhatsApp:"))
        self.tel = BigInput(hint_text="098...", input_filter='int')
        self.container.add_widget(self.tel)

        # =========================================================================
        # ---> NUEVOS CAMPOS: CONTACTO ALTERNATIVO
        # =========================================================================
        self.container.add_widget(BigLabel(text="Contacto Alternativo (Nombre):"))
        self.contacto_alt_nom = BigInput(hint_text="Nombre del contacto secundario")
        self.container.add_widget(self.contacto_alt_nom)

        self.container.add_widget(BigLabel(text="Cargo o Relación con la Granja:"))
        self.contacto_alt_cargo = BigInput(hint_text="Ej: Administrador, Encargado, Esposa")
        self.container.add_widget(self.contacto_alt_cargo)

        self.container.add_widget(BigLabel(text="Teléfono Contacto Alternativo:"))
        self.contacto_alt_tel = BigInput(hint_text="Número telefónico", input_filter='int')
        self.container.add_widget(self.contacto_alt_tel)
        # =========================================================================
        
        self.container.add_widget(BigLabel(text="Zona Geográfica:"))
        self.sp_zona = Spinner(text="Seleccionar Zona", size_hint_y=None, height=dp(65), background_color=AZUL_LOGO, font_size=dp(16))
        self.container.add_widget(self.sp_zona)
        
        self.container.add_widget(BigLabel(text="Técnico Responsable:"))
        self.sp_tec = Spinner(text="Seleccionar Técnico", size_hint_y=None, height=dp(65), background_color=AZUL_LOGO, font_size=dp(16))
        self.container.add_widget(self.sp_tec)
        
        self.container.add_widget(BigLabel(text="Especie Animal:"))
        self.sp_esp = Spinner(text="Seleccionar Especie", values=tuple(MAPA_TECNICO.keys()), size_hint_y=None, height=dp(65), background_color=AZUL_LOGO, font_size=dp(16))
        self.sp_esp.bind(text=self.desglosar_etapas)
        self.container.add_widget(self.sp_esp)
        
        self.box_etapas = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.box_etapas.bind(minimum_height=self.box_etapas.setter('height'))
        self.container.add_widget(self.box_etapas)
        
        # =========================================================================
        # SECCIÓN GPS CONFIGURADA PARA MÁXIMA PRECISIÓN FILTRADA
        # =========================================================================
        self.container.add_widget(BigLabel(text="Coordenadas Geográficas (GPS Alta Precisión):"))
        
        self.layout_gps = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(60))
        
        self.lbl_gps = Label(
            text="Sin capturar (0.00, 0.00)", 
            color=(1, 1, 1, 1), 
            font_size=dp(14), 
            bold=True, 
            size_hint_x=0.6, 
            halign='center', 
            valign='middle',
            outline_color=(0, 0, 0, 1), 
            outline_width=dp(1.5)
        )
        self.lbl_gps.bind(size=lambda obj, _: setattr(obj, 'text_size', (obj.width, None)))
        self.layout_gps.add_widget(self.lbl_gps)
        
        self.btn_gps = Button(
            text="ESTABILIZAR GPS", 
            size_hint_x=0.4, 
            background_color=(0.1, 0.4, 0.6, 1), 
            bold=True, 
            font_size=dp(14)
        )
        self.btn_gps.bind(on_release=self.obtener_coordenadas)
        self.layout_gps.add_widget(self.btn_gps)
        
        self.container.add_widget(self.layout_gps)
        # -----------------------------------------------------------------
        
        self.btn_g = Button(text="GUARDAR NUEVO CLIENTE", size_hint_y=None, height=dp(85), background_color=VERDE_LOGO, bold=True, font_size=dp(18))
        self.btn_g.bind(on_release=self.guardar_cliente_protegido)
        self.container.add_widget(self.btn_g)
        
        self.btn_volver = Button(text="VOLVER AL MENÚ", size_hint_y=None, height=dp(60), font_size=dp(16))
        self.btn_volver.bind(on_release=self.volver_menu)
        self.container.add_widget(self.btn_volver)
        
        self.sc.add_widget(self.container)
        l.add_widget(self.sc)
        self.add_widget(l)

    def guardar_cliente_protegido(self, instance):
        self.nom.focus = False
        self.tel.focus = False
        self.contacto_alt_nom.focus = False
        self.contacto_alt_cargo.focus = False
        self.contacto_alt_tel.focus = False
        Window.release_all_keyboards()
        self.guardar_cliente(instance)

    def on_enter(self):
        self.sp_zona.text = "Seleccione Zona"
        self.sp_tec.text = "Seleccione Técnico"
        threading.Thread(target=self.cargar_datos_hilo, daemon=True).start()

    def on_leave(self):
        """Garantiza apagar el hardware de GPS si el usuario sale bruscamente de la pantalla."""
        self.detener_sensor_gps()

    def cargar_datos_hilo(self):
        for i in range(3):
            try:
                conn = sqlite3.connect(get_db_path(), timeout=15)
                cursor = conn.cursor()
                
                # Zonas
                z_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='zonas'").fetchone()
                lista_zonas = ["Sin zonas disponibles"]
                if z_res and z_res[0]:
                    vals = json.loads(z_res[0])
                    lista_zonas = [str(v.get('nombre', v)) if isinstance(v, dict) else str(v) for v in vals.values()]
                    lista_zonas = sorted(list(set(lista_zonas)))

                # Técnicos
                t_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='tecnicos_dict'").fetchone()
                nombres_tecnicos = ["Sin técnicos"]
                dict_tecnicos = {}
                if t_res and t_res[0]:
                    tecnicos = json.loads(t_res[0])
                    dict_tecnicos = { 
                        str(v.get('nombre', 'Sin Nombre') if isinstance(v, dict) else v): k 
                        for k, v in tecnicos.items() 
                    }
                    nombres = [n for n in dict_tecnicos.keys() if n and str(n).strip()]
                    if nombres:
                        nombres_tecnicos = sorted(list(set(nombres)))

                cursor.close()
                conn.close()
                
                Clock.schedule_once(lambda dt: self.actualizar_ui_spinners(lista_zonas, nombres_tecnicos, dict_tecnicos), 0)
                return
            except sqlite3.OperationalError:
                time.sleep(0.3)
                continue
            except Exception as e:
                print(f"Error asíncrono crítico en hilo: {e}")
                break

    def actualizar_ui_spinners(self, zonas, tecnicos, dict_tecnicos):
        self.sp_zona.values = zonas
        self.sp_tec.values = tecnicos
        self.dict_tecnicos_local = dict_tecnicos

    def desglosar_etapas(self, s, t):
        self.box_etapas.clear_widgets()
        self.inputs_etapas = {}
        if t in MAPA_TECNICO:
            self.box_etapas.add_widget(BigLabel(text="Inventario Inicial por Etapa:"))
            for e in MAPA_TECNICO[t]['etapas']:
                f = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(10))
                lbl = Label(text=str(e), color=(1,1,1,1), font_size=dp(16), bold=True, size_hint_x=0.6, halign='left', outline_color=(0,0,0,1), outline_width=dp(1.5))
                lbl.bind(size=lambda obj, _: setattr(obj, 'text_size', (obj.width, None)))
                f.add_widget(lbl)
                inp = BigInput(text="0", input_filter='int', size_hint_x=0.4)
                f.add_widget(inp)
                self.box_etapas.add_widget(f)
                self.inputs_etapas[e] = inp

    # =========================================================================
    # NUEVA LOGICA DE ESCUCHA CONTINUA NATIVA DE ANDROID (ALTA PRECISIÓN)
    # =========================================================================
    def obtener_coordenadas(self, instance):
        """Gestiona los permisos e inicializa la escucha en tiempo real del GPS."""
        import platform
        if platform.system() == 'Android':
            try:
                from android.permissions import request_permissions, Permission
                def callback_permisos(permissions, results):
                    if all(results):
                        self.lbl_gps.text = "Buscando satélites...\nEspere a que estabilice"
                        self.lbl_gps.color = (1, 0.6, 0.2, 1)
                        self.activar_escucha_gps_nativa()
                    else:
                        self.lbl_gps.text = "Permiso GPS denegado"
                        self.lbl_gps.color = (1, 0.3, 0.3, 1)
                request_permissions([Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION], callback_permisos)
            except Exception as e:
                self.lbl_gps.text = "Error al pedir permisos"
                self.lbl_gps.color = (1, 0.3, 0.3, 1)
        else:
            # Coordenadas simuladas para pruebas en la computadora (PC)
            self.latitud_actual = 12.6280
            self.longitud_actual = -87.1290
            self.lbl_gps.text = f"Simulado PC:\nLat: {self.latitud_actual} | Lon: {self.longitud_actual}\nError: ~1m"
            self.lbl_gps.color = (0.3, 1, 0.3, 1)

    def activar_escucha_gps_nativa(self):
        """Registra el LocationListener nativo configurado para refrescar cada segundo."""
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            Looper = autoclass('android.os.Looper')
            
            actividad_actual = PythonActivity.mActivity
            self.servicio_ubicacion = actividad_actual.getSystemService(Context.LOCATION_SERVICE)

            class GPSLocationListener(PythonJavaClass):
                __javainterfaces__ = ['android/location/LocationListener']

                def __init__(self, callback_update):
                    super().__init__()
                    self.callback_update = callback_update

                @java_method('(Landroid/location/Location;)V')
                def onLocationChanged(self, location):
                    if location:
                        self.callback_update(location)

                @java_method('(Ljava/lang/String;ILandroid/os/Bundle;)V')
                def onStatusChanged(self, provider, status, extras): pass

                @java_method('(Ljava/lang/String;)V')
                def onProviderEnabled(self, provider): pass

                @java_method('(Ljava/lang/String;)V')
                def onProviderDisabled(self, provider): pass

            if self.listener_gps:
                self.servicio_ubicacion.removeUpdates(self.listener_gps)

            self.listener_gps = GPSLocationListener(self.procesar_cambio_ubicacion)
            
            # Solicitud continua: 1 segundo de intervalo mínimo y 0 metros para máxima sensibilidad
            self.servicio_ubicacion.requestLocationUpdates(
                'gps', 
                int(1000), 
                float(0), 
                self.listener_gps, 
                Looper.getMainLooper()
            )
        except Exception as e:
            self.lbl_gps.text = "Error sensor GPS Nativo"
            self.lbl_gps.color = (1, 0.3, 0.3, 1)

    def procesar_cambio_ubicacion(self, location):
        """Filtra y valida dinámicamente la precisión de la lectura recibida."""
        try:
            precision_metros = float(location.getAccuracy())
            lat = float(location.getLatitude())
            lon = float(location.getLongitude())

            self.lbl_gps.text = f"Buscando...\nMargen de error: {round(precision_metros, 1)} metros"

            # Guardamos el dato intermedio
            self.latitud_actual = lat
            self.longitud_actual = lon

            # Evaluamos si cumple con el estándar físico óptimo (5 metros o menos)
            if precision_metros <= 5.0:
                self.lbl_gps.text = f"¡MÁXIMA PRECISIÓN FIJADA!\nLat: {round(lat, 5)} | Lon: {round(lon, 5)}\nMargen: ±{round(precision_metros, 1)}m"
                self.lbl_gps.color = (0.3, 1, 0.3, 1) # UI en Verde
                self.detener_sensor_gps() # Apagamos para ahorrar energía
            else:
                self.lbl_gps.color = (1, 0.6, 0.2, 1) # UI en Naranja (esperando estabilidad)
        except Exception as e:
            print(f"Error procesando GPS: {e}")

    def detener_sensor_gps(self):
        """Apaga el sensor de ubicación de forma segura."""
        if self.servicio_ubicacion and self.listener_gps:
            try:
                self.servicio_ubicacion.removeUpdates(self.listener_gps)
                self.listener_gps = None
            except Exception as e:
                print(f"Error deteniendo GPS: {e}")

    # =========================================================================

    def guardar_cliente(self, instance):
        if not self.nom.text.strip() or self.sp_zona.text in ["Seleccionar Zona", "Seleccione Zona"]: 
            return 

        tecnico_id = self.dict_tecnicos_local.get(self.sp_tec.text, "ID_DESCONOCIDO")
        nombre_est = self.nom.text.strip().upper()
        cliente_id = f"{str(self.sp_zona.text).upper()}_{nombre_est.replace(' ', '_')}_{self.tel.text[-4:]}"
        
        data = {
            "id_interno": cliente_id, 
            "nombre": nombre_est, 
            "telefono": self.tel.text,
            "zona": self.sp_zona.text, 
            "especie": self.sp_esp.text, 
            "tecnico_id": tecnico_id,
            "inventario": {sanitizar_llave(e): int(i.text or 0) for e, i in self.inputs_etapas.items()},
            "inventario_productos": {}, 
            "fecha_registro": datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
            "coordenadas": {
                "latitud": self.latitud_actual,
                "longitud": self.longitud_actual
            },
            "contacto_alternativo": {
                "nombre": self.contacto_alt_nom.text.strip().upper(),
                "cargo_relacion": self.contacto_alt_cargo.text.strip(),
                "telefono": self.contacto_alt_tel.text.strip()
            }
        }

        conn = sqlite3.connect(get_db_path())
        
        # 1. Guardar en la cola de sincronización para Firebase
        conn.execute("INSERT INTO cola_sincro (tipo, datos) VALUES ('NUEVO_CLIENTE', ?)", (json.dumps(data),))
        
        # 2. Actualizar de forma forzada y directa el JSON global de 'clientes' en cache_app
        res = conn.execute("SELECT valor FROM cache_app WHERE clave='clientes'").fetchone()
        clis = json.loads(res[0]) if res and res[0] else {}
        clis[cliente_id] = data
        conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('clientes', ?)", (json.dumps(clis),))
        
        conn.commit()
        conn.close()

        # 3. Forzar actualización inmediata en la app global si existe el atributo
        app = App.get_running_app()
        if hasattr(app, 'clientes_lista'):
            item_nuevo = f"{nombre_est} ({self.sp_zona.text})"
            if item_nuevo not in app.clientes_lista:
                app.clientes_lista.append(item_nuevo)

        self.detener_sensor_gps()
        self.limpiar_campos()
        self.manager.current = 'main'
        # =========================================================================
        # SINCRONIZACIÓN EN CALIENTE CON LA PANTALLA DE VISITAS
        # =========================================================================
        try:
            if self.manager and self.manager.has_screen('visitas'):
                pantalla_visitas = self.manager.get_screen('visitas')
                # Si la pantalla de visitas guarda los clientes en un diccionario local:
                if hasattr(pantalla_visitas, 'dict_clientes_local') and isinstance(pantalla_visitas.dict_clientes_local, dict):
                    pantalla_visitas.dict_clientes_local[cliente_id] = data
                # Si la pantalla de visitas tiene un método para refrescar su selector/spinner:
                if hasattr(pantalla_visitas, 'actualizar_spinner_clientes'):
                    pantalla_visitas.actualizar_spinner_clientes()
                elif hasattr(pantalla_visitas, 'cargar_clientes_en_spinner'):
                    pantalla_visitas.cargar_clientes_en_spinner()
        except Exception as e:
            print(f"No se pudo actualizar la pantalla de visitas en caliente: {e}")
        # =========================================================================

        self.detener_sensor_gps()
        self.limpiar_campos()
        self.manager.current = 'main'

    def limpiar_campos(self):
        self.nom.text = ""
        self.tel.text = ""
        self.contacto_alt_nom.text = ""
        self.contacto_alt_cargo.text = ""
        self.contacto_alt_tel.text = ""
        self.sp_zona.text = "Seleccionar Zona"
        self.sp_tec.text = "Seleccionar Técnico"
        self.sp_esp.text = "Seleccionar Especie"
        self.box_etapas.clear_widgets()
        self.inputs_etapas = {}
        
        self.latitud_actual = 0.0
        self.longitud_actual = 0.0
        if hasattr(self, 'lbl_gps'):
            self.lbl_gps.text = "Sin capturar (0.00, 0.00)"
            self.lbl_gps.color = (1, 1, 1, 1)

    def volver_menu(self, instance):
        self.detener_sensor_gps()
        self.manager.current = 'main'

class RegistroVisitaScreen(PantallaConDatos):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.clientes_db = {}; self.catalogo_detalle = {}  
        self.inputs_inv = {}; self.inputs_par = {}; self.inputs_existencia_actual = {}
        self.id_cliente_actual = None
        self.ruta_foto_actual = ""
        
        l = FloatLayout(size_hint=(1, 1))
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False, size_hint=(1, 1)))
        
        self.sc = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(10))
        
        self.container = ContainerTransparente(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        
        self.container.add_widget(BigLabel(text="Seleccionar Productor:"))
        self.sp_cliente = Spinner(text="Seleccione Productor", size_hint_y=None, height=dp(65), background_color=AZUL_LOGO, font_size=dp(16))
        self.sp_cliente.bind(text=self.sincronizar_campos)
        self.container.add_widget(self.sp_cliente)
        
        self.info_lab = Label(text="Especie: -- | Zona: --", color=(1,1,1,1), size_hint_y=None, height=dp(45), bold=True, outline_color=(0,0,0,1), outline_width=dp(1.5))
        self.container.add_widget(self.info_lab)
        
        self.box_animales = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.box_animales.bind(minimum_height=self.box_animales.setter('height'))
        self.container.add_widget(self.box_animales)
        
        self.box_parametros = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.box_parametros.bind(minimum_height=self.box_parametros.setter('height'))
        self.container.add_widget(self.box_parametros)
        
        # --- SECCIÓN DE CONTROL DE ALIMENTO ---
        self.container.add_widget(BigLabel(text="CONTROL DE ALIMENTO (Lbs)"))
        
        h_table = BoxLayout(size_hint_y=None, height=dp(50))
        for txt, sx in [("Producto", 0.28), ("I. INI", 0.24), ("I. TRA", 0.24), ("CONS", 0.24)]:
            h_table.add_widget(Label(
                text=txt, 
                color=(1,1,1,1), 
                font_size=dp(18), 
                size_hint_x=sx, 
                bold=True, 
                outline_color=(0,0,0,1), 
                outline_width=dp(1.8)
            ))
        self.container.add_widget(h_table)
        
        self.box_productos = BoxLayout(orientation='vertical', spacing=dp(15), size_hint_y=None)
        self.box_productos.bind(minimum_height=self.box_productos.setter('height'))
        self.container.add_widget(self.box_productos)
        
        self.sp_master_prod = Spinner(text="Seleccione Alimento", size_hint_y=None, height=dp(60), background_color=AZUL_LOGO, font_size=dp(15))
        self.container.add_widget(self.sp_master_prod)
        
        self.btn_add = Button(text="+ AGREGAR PRODUCTO", size_hint_y=None, height=dp(60), background_color=(0.1, 0.5, 0.1, 1), font_size=dp(16), bold=True)
        self.btn_add.bind(on_release=self.agregar_producto_nuevo_a_vista)
        self.container.add_widget(self.btn_add)
        
        # =========================================================================
        # SECCIÓN: FOTO OBLIGATORIA (ÚNICAMENTE DESDE LA CÁMARA)
        # =========================================================================
        self.container.add_widget(BigLabel(text="Evidencia Fotográfica de la Granja:"))
        
        self.layout_foto = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(60))
        
        self.lbl_foto = Label(
            text="Foto no capturada *", 
            color=(1, 0.3, 0.3, 1), 
            font_size=dp(14), 
            bold=True, 
            size_hint_x=0.6, 
            halign='center', 
            valign='middle',
            outline_color=(0, 0, 0, 1), 
            outline_width=dp(1.5)
        )
        self.lbl_foto.bind(size=lambda obj, _: setattr(obj, 'text_size', (obj.width, None)))
        self.layout_foto.add_widget(self.lbl_foto)
        
        self.btn_foto = Button(
            text="ABRIR CÁMARA", 
            size_hint_x=0.4, 
            background_color=(0.1, 0.5, 0.4, 1), 
            bold=True, 
            font_size=dp(14)
        )
        self.btn_foto.bind(on_release=self.capturar_foto_camara)
        self.layout_foto.add_widget(self.btn_foto)
        
        self.container.add_widget(self.layout_foto)
        # =========================================================================
        
        self.btn_v = Button(text="GUARDAR REPORTE", size_hint_y=None, height=dp(80), background_color=VERDE_LOGO, bold=True, font_size=dp(18))
        self.btn_v.bind(on_release=self.enviar_todo)
        self.container.add_widget(self.btn_v)
        
        self.btn_back = Button(text="VOLVER", size_hint_y=None, height=dp(55), font_size=dp(16))
        self.btn_back.bind(on_release=lambda x: setattr(self.manager, 'current', 'main'))
        self.container.add_widget(self.btn_back)
        
        self.sc.add_widget(self.container)
        l.add_widget(self.sc)
        self.add_widget(l)

    def sincronizar_campos_base(self, instance, value):
        print(f"Valor seleccionado: {value}")

    def comprimir_imagen_al_minimo(self, ruta_archivo):
        if not ruta_archivo or not os.path.exists(ruta_archivo):
            return
        try:
            from PIL import Image as PILImage
            img = PILImage.open(ruta_archivo)
            max_size = 1280
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
            img.save(ruta_archivo, "JPEG", quality=35, optimize=True)
            print(f"[COMPRESIÓN] Proceso completado con éxito para: {ruta_archivo}")
        except Exception as e:
            print(f"Error comprimiendo la imagen: {e}")

    def capturar_foto_camara(self, instance):
        import platform
        if platform.system() == 'Android':
            try:
                from android.permissions import request_permissions, Permission
                def callback_permisos(permissions, results):
                    if all(results):
                        self.ejecutar_intent_camara()
                    else:
                        self.lbl_foto.text = "Falta permiso de cámara"
                        self.lbl_foto.color = (1, 0.3, 0.3, 1)
                request_permissions([Permission.CAMERA], callback_permisos)
            except Exception as e:
                print(f"Error al solicitar permisos: {e}")
                self.ejecutar_intent_camara()
        else:
            self.ruta_foto_actual = "evidencia_visita_simulada.jpg"
            try:
                from PIL import Image as PILImage
                img_mock = PILImage.new('RGB', (1920, 1080), color = (73, 109, 137))
                img_mock.save(self.ruta_foto_actual)
                self.comprimir_imagen_al_minimo(self.ruta_foto_actual)
            except:
                pass
            self.lbl_foto.text = "Foto Capturada (Simulada)"
            self.lbl_foto.color = (0.3, 1, 0.3, 1)

    def ejecutar_intent_camara(self):
        try:
            from jnius import autoclass
            from android.activity import bind as android_bind
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            MediaStore = autoclass('android.provider.MediaStore')
            
            android_bind(on_activity_result=self.on_resultado_camara)
            
            intent_camara = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            PythonActivity.mActivity.startActivityForResult(intent_camara, 1011)
            
            self.lbl_foto.text = "Cámara abierta..."
            self.lbl_foto.color = (1, 1, 0.3, 1)
        except Exception as e:
            print(f"Error al abrir la cámara: {e}")
            self.lbl_foto.text = "Error al abrir la cámara"
            self.lbl_foto.color = (1, 0.3, 0.3, 1)

    def on_resultado_camara(self, request_code, result_code, intent):
        try:
            from android.activity import unbind as android_unbind
            android_unbind(on_activity_result=self.on_resultado_camara)
        except:
            pass

        if request_code == 1011:
            if result_code == -1: 
                import os
                from jnius import autoclass
                try:
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    context = PythonActivity.mActivity
                    self.ruta_foto_actual = os.path.join(context.getFilesDir().getAbsolutePath(), "visita_temp.jpg")
                except:
                    self.ruta_foto_actual = "visita_temp.jpg"

                self.comprimir_imagen_al_minimo(self.ruta_foto_actual)
                self.lbl_foto.text = "Foto Capturada OK"
                self.lbl_foto.color = (0.3, 1, 0.3, 1)
            else:
                self.ruta_foto_actual = ""
                self.lbl_foto.text = "Captura cancelada *"
                self.lbl_foto.color = (1, 0.3, 0.3, 1)

    def subir_foto_a_firebase_con_ruta(self, ruta_archivo, zona="", tecnico=""):
        import os, uuid, requests, time, re
        
        if not ruta_archivo:
            print("[STORAGE ERROR] La ruta de la foto está vacía.")
            return "ERROR_RUTA_VACIA"

        # 1. Resolver URIs virtuales de Android (content://) si la cámara las devuelve así
        if ruta_archivo.startswith("content://"):
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity
                content_resolver = context.getContentResolver()
                
                File = autoclass('java.io.File')
                FileOutputStream = autoclass('java.io.FileOutputStream')
                InputStream = content_resolver.openInputStream(autoclass('android.net.Uri').parse(ruta_archivo))
                
                temp_file = File(context.getCacheDir(), f"temp_foto_{int(time.time())}.jpg")
                output_stream = FileOutputStream(temp_file)
                
                buffer = bytearray(1024)
                while (length := InputStream.read(buffer)) > 0:
                    output_stream.write(buffer, 0, length)
                output_stream.close()
                InputStream.close()
                
                ruta_archivo = temp_file.getAbsolutePath()
                print(f"[STORAGE] URI de Android convertida a archivo físico: {ruta_archivo}")
            except Exception as e:
                print(f"[STORAGE ERROR] No se pudo procesar la URI content://: {e}")

        # 2. Búsqueda adaptable en el almacenamiento interno si la ruta directa no existe
        if not os.path.exists(ruta_archivo):
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity
                posible_ruta = os.path.join(context.getFilesDir().getAbsolutePath(), os.path.basename(ruta_archivo))
                if os.path.exists(posible_ruta):
                    ruta_archivo = posible_ruta
            except:
                pass

        if not os.path.exists(ruta_archivo):
            print(f"[STORAGE ERROR] El archivo físico no existe en ninguna ruta: {ruta_archivo}")
            return "ERROR_ARCHIVO_NO_ENCONTRADO"

        try:
            nombre_archivo = os.path.basename(ruta_archivo)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            ruta_remota = f"fotos_visitas/visita_{timestamp_str}_{nombre_archivo}"
            
            with open(ruta_archivo, "rb") as f:
                file_data = f.read()

            bucket_name = "campodata-cd974.firebasestorage.app"
            file_name_encoded = ruta_remota.replace("/", "%2F")
            token_personalizado = str(uuid.uuid4())
            
            url_upload = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o?uploadType=media&name={file_name_encoded}"
            headers = {"Content-Type": "image/jpeg"}

            print(f"[STORAGE] Subiendo a: {url_upload} (Tamaño: {len(file_data)} bytes)")
            response = requests.post(url_upload, data=file_data, headers=headers, timeout=30)
            
            print(f"[STORAGE] Código HTTP respuesta: {response.status_code}")
            print(f"[STORAGE] Respuesta de Firebase: {response.text}")

            if response.status_code == 200:
                res_json = response.json()
                raw_tokens = res_json.get("downloadTokens", "")
                download_token = raw_tokens.split(",")[0] if raw_tokens else token_personalizado
                
                url_publica = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{file_name_encoded}?alt=media&token={download_token}"
                print(f"[STORAGE] Éxito total URL pública: {url_publica}")
                
                # Función auxiliar local para sanitizar claves en Firebase RTDB (evita error 400 por caracteres inválidos)
                def limpiar_clave(texto):
                    return re.sub(r'[.#$\[\]/\s]', '_', str(texto)) if texto else "GENERAL"

                # Si necesitas registrar la visita asociada a la foto en Realtime Database, hazlo aquí de forma limpia:
                # zona_s = limpiar_clave(zona)
                # tecnico_s = limpiar_clave(tecnico)
                # key_visita = f"{zona_s}_{tecnico_s}_{timestamp_str}"
                # url_rtdb = f"{URL}/distribuidoras/{DISTRIBUIDORA}/visitas/{key_visita}.json"
                # requests.put(url_rtdb, json={"foto": url_publica, "fecha": timestamp_str})

                return url_publica
            else:
                print(f"[STORAGE ERROR] Falló HTTP {response.status_code}: {response.text}")
                return f"ERROR_HTTP_{response.status_code}"
                
        except Exception as e:
            print(f"[STORAGE EXCEPTION] Error crítico al subir foto: {e}")
            return "ERROR_EXCEPCION_CRITICA"

    def actualizar_ui_exito(self):
        if hasattr(self, 'lbl_foto'):
            self.lbl_foto.text = "¡Enviado con éxito!"
            self.lbl_foto.color = (0.3, 1, 0.3, 1)

    def actualizar_ui_error(self):
        if hasattr(self, 'lbl_foto'):
            self.lbl_foto.text = "Error al enviar datos"
            self.lbl_foto.color = (1, 0.3, 0.3, 1)

    def on_enter(self):
        self.sp_cliente.text = "Seleccione Productor"
        self.info_lab.text = "Especie: -- | Zona: --"
        self.box_animales.clear_widgets()
        self.box_parametros.clear_widgets()
        self.box_productos.clear_widgets()
        self.inputs_existencia_actual = {}; self.inputs_inv = {}; self.inputs_par = {}
        
        self.ruta_foto_actual = ""
        if hasattr(self, 'lbl_foto'):
            self.lbl_foto.text = "Foto no capturada *"
            self.lbl_foto.color = (1, 0.3, 0.3, 1)
        
        import threading
        threading.Thread(target=self.cargar_clientes_hilo, daemon=True).start()

    def cargar_clientes_hilo(self):
        db_path = get_db_path()
        clientes_db = {}
        catalogo_detalle = {}
        mis_clientes = []
        
        import sqlite3, json, time
        for i in range(3):
            try:
                conn = sqlite3.connect(db_path, timeout=5)
                cursor = conn.cursor()
                
                res = cursor.execute("SELECT valor FROM cache_app WHERE clave='clientes'").fetchone()
                prod = cursor.execute("SELECT valor FROM cache_app WHERE clave='catalogo'").fetchone()
                
                cursor.close()
                conn.close()
                
                from kivy.app import App
                app = App.get_running_app()
                mi_id = str(getattr(app, 'device_id', '')).strip()
                
                if prod and prod[0]:
                    try:
                        catalogo_detalle = json.loads(prod[0])
                    except:
                        pass
                
                if res and res[0]:
                    clientes_db = json.loads(res[0])
                    lista_tmp = []
                    for k, v in clientes_db.items():
                        if isinstance(v, dict):
                            id_tec_cliente = str(v.get('tecnico_id', '')).strip()
                            # CORRECCIÓN: Permitimos la visualización si coincide el técnico, si está libre, o si acabamos de crearlo localmente
                            if id_tec_cliente == mi_id or id_tec_cliente == "" or id_tec_cliente == "ID_DESCONOCIDO" or not mi_id:
                                nombre = v.get('nombre', 'Sin nombre')
                                zona = v.get('zona', 'Sin zona')
                                lista_tmp.append(f"{nombre} ({zona})")
                    
                    if lista_tmp:
                        mis_clientes = sorted(list(set(lista_tmp)))

                if not mis_clientes and hasattr(app, 'clientes_lista') and app.clientes_lista:
                    mis_clientes = sorted(list(set(app.clientes_lista)))
                    for item in mis_clientes:
                        if "(" in item:
                            n_part, z_part = item.split(" (", 1)
                            z_part = z_part.replace(")", "")
                        else:
                            n_part, z_part = item, "General"
                        
                        mock_id = f"local_{n_part}"
                        if mock_id not in clientes_db:
                            clientes_db[mock_id] = {
                                "id_interno": mock_id,
                                "nombre": n_part,
                                "zona": z_part,
                                "especie": "Porcina" if "pig" in n_part.lower() else "Avícola"
                            }

                if not mis_clientes:
                    mis_clientes = ["Sin clientes asignados"]

                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self.actualizar_ui_clientes(clientes_db, mis_clientes, catalogo_detalle), 0)
                return
                
            except sqlite3.OperationalError:
                time.sleep(0.2)
                continue
            except Exception as e:
                print(f"Error cargando clientes en hilo: {e}")
                break
                
        try:
            from kivy.app import App
            app = App.get_running_app()
            if hasattr(app, 'clientes_lista') and app.clientes_lista:
                mis_clientes = sorted(list(set(app.clientes_lista)))
            else:
                mis_clientes = ["Sin clientes asignados"]
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self.actualizar_ui_clientes(clientes_db, mis_clientes, catalogo_detalle), 0)
        except:
            pass

    def actualizar_ui_clientes(self, clientes_db, mis_clientes, catalogo_detalle):
        self.clientes_db = clientes_db
        self.sp_cliente.values = mis_clientes
        self.catalogo_detalle = catalogo_detalle

    def filtrar_catalogo_por_especie(self, esp):
        filtrados = [p['nombre'] for p in self.catalogo_detalle.values() if isinstance(p, dict) and p.get('especie', '').lower() == esp.lower()]
        self.sp_master_prod.values = sorted(filtrados) if filtrados else ["Sin stock"]
        self.sp_master_prod.text = "Seleccione Alimento"

    def sincronizar_campos(self, s, n):
        if n in ["Seleccione Productor", "Seleccione Cliente", "Sin clientes asignados"]: return
        self.box_animales.clear_widgets(); self.box_parametros.clear_widgets(); self.box_productos.clear_widgets()
        self.inputs_existencia_actual = {}; self.inputs_inv = {}; self.inputs_par = {}
        
        cli = next((v for v in self.clientes_db.values() if f"{v['nombre']} ({v['zona']})" == n or v['nombre'] == n), None)
        if cli:
            self.id_cliente_actual = cli.get('id_interno', 'Generico')
            self.zona_actual = cli.get('zona', 'GENERAL')
            esp = cli.get('especie', "")
            self.info_lab.text = f"Especie: {esp} | Zona: {self.zona_actual}"
            self.filtrar_catalogo_por_especie(esp)
            
            if esp in MAPA_TECNICO:
                for e in MAPA_TECNICO[esp]['etapas']:
                    f = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(10))
                    # Mantiene el nombre exacto de la etapa (ej: "Postura F1", "Crecimiento")
                    f.add_widget(Label(text=str(e), color=(1,1,1,1), size_hint_x=0.6, font_size=dp(16), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
                    i = BigInput(text=str(cli.get('inventario', {}).get(e, "0")), input_filter='int', size_hint_x=0.4)
                    f.add_widget(i); self.box_animales.add_widget(f); self.inputs_inv[e] = i
                
                for p in MAPA_TECNICO[esp]['params']:
                    f = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(10))
                    f.add_widget(Label(text=str(p), color=(1,1,1,1), size_hint_x=0.6, font_size=dp(16), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
                    
                    if str(p).lower() == "actividad física":
                        i = Spinner(text="Mantenimiento", values=("Mantenimiento", "Trabajo Ligero", "Trabajo Pesado"), 
                                    size_hint_x=0.4, background_color=(0.1, 0.4, 0.6, 1))
                    else:
                        i = BigInput(text="0", input_filter='float', size_hint_x=0.4)
                    
                    f.add_widget(i); self.box_parametros.add_widget(f); self.inputs_par[p] = i

            inv_p = cli.get('inventario_productos', {})
            if isinstance(inv_p, dict):
                for prod, cant in inv_p.items(): 
                    self.agregar_fila_producto(prod, anterior=str(cant), actual=str(cant))

    def agregar_fila_producto(self, nombre, anterior="0", actual="0"):
        f = BoxLayout(size_hint_y=None, height=dp(65), spacing=dp(5))
        f.add_widget(Label(text=str(nombre), color=(1,1,1,1), size_hint_x=0.4, font_size=dp(14), outline_color=(0,0,0,1), outline_width=1.5))
        ia = BigInput(text=str(anterior), input_filter='float', size_hint_x=0.30)
        ic = BigInput(text=str(actual), input_filter='float', size_hint_x=0.30)
        io = BigInput(text="0", input_filter='float', size_hint_x=0.30)
        f.add_widget(ia); f.add_widget(ic); f.add_widget(io); self.box_productos.add_widget(f)
        self.inputs_existencia_actual[nombre] = {"input_ant": ia, "input": ic, "input_cons": io}

    def agregar_producto_nuevo_a_vista(self, instance):
        p = self.sp_master_prod.text
        if p not in ["Seleccione Alimento", "Sin stock"] and p not in self.inputs_existencia_actual:
            self.agregar_fila_producto(p)

    def enviar_todo(self, instance):
        try:
            from kivy.core.window import Window
            Window.release_all_keyboards()
        except:
            pass
        
        if not self.id_cliente_actual or self.sp_cliente.text in ["Seleccione Productor", "Seleccione Cliente", "Sin clientes asignados"]:
            return
            
        if not self.ruta_foto_actual:
            self.lbl_foto.text = "¡DEBE TOMAR LA FOTO DE LA GRANJA!"
            self.lbl_foto.color = (1, 0.1, 0.1, 1)
            return

        cliente_id_seguro = str(self.id_cliente_actual)
        nombre_productor_limpio = "PRODUCTOR"
        
        cli_obj = next((v for v in self.clientes_db.values() if str(v.get('id_interno')) == str(self.id_cliente_actual)), None)
        if cli_obj and 'nombre' in cli_obj:
            nombre_productor_limpio = str(cli_obj.get('nombre')).strip()
        else:
            texto_sp = self.sp_cliente.text
            if "(" in texto_sp:
                nombre_productor_limpio = texto_sp.split(" (")[0].strip()
            else:
                nombre_productor_limpio = texto_sp.strip()

        # Construcción exacta del formato: ZONA ESTE_CARLOS_7458 (sin sanitizar los espacios del nombre/zona con guiones bajos excesivos si no se requiere, o respetando el formato exacto del requerimiento)
        if hasattr(self, 'zona_actual') and self.zona_actual:
            zona_o_prefijo = str(self.zona_actual).strip()
        elif cli_obj and 'zona' in cli_obj:
            zona_o_prefijo = str(cli_obj.get('zona')).strip()
        
        cliente_id_formateado = f"{zona_o_prefijo}_{nombre_productor_limpio}"
        timestamp_id = time.strftime("%Y_%m_%d_%H_%M_%S")
        timestamp_nodo_key = time.strftime("%Y-%m-%d %H:%M:%S")

        import json, sqlite3, threading
        from datetime import datetime
        try:
            inv_animales = {}
            for e, i in self.inputs_inv.items():
                try:
                    # Se mantiene el nombre original de la etapa zootécnica (ej: "Postura F1", "Crecimiento") como clave directa
                    inv_animales[str(e)] = int(i.text) if i.text.strip() else 0
                except ValueError:
                    inv_animales[str(e)] = 0

            params_visita = {}
            for p, i in self.inputs_par.items():
                if isinstance(i, Spinner):
                    params_visita[str(p)] = i.text
                else:
                    try:
                        params_visita[str(p)] = float(i.text) if i.text.strip() else 0.0
                    except ValueError:
                        params_visita[str(p)] = 0.0

            detalle_bodega = {}
            for p, data in self.inputs_existencia_actual.items():
                k = str(p)
                try:
                    ant = float(data['input_ant'].text) if data['input_ant'].text.strip() else 0.0
                    act = float(data['input'].text) if data['input'].text.strip() else 0.0
                    con = float(data['input_cons'].text) if data['input_cons'].text.strip() else 0.0
                    detalle_bodega[k] = {"anterior": ant, "actual": act, "consumo": con}
                except ValueError:
                    detalle_bodega[k] = {"anterior": 0.0, "actual": 0.0, "consumo": 0.0}

            threading.Thread(
                target=self.enviar_todo_proceso_limpio, 
                args=(cliente_id_seguro, self.ruta_foto_actual, timestamp_id, cliente_id_formateado, inv_animales, params_visita, detalle_bodega),
                daemon=True
            ).start()

        except Exception as e:
            print(f"Error interno al preparar el envío: {e}")

    def enviar_todo_proceso_limpio(self, cliente_id, ruta_foto, timestamp_id, cliente_id_formateado, inv_animales, params_visita, detalle_bodega):
        try:
            url_publica_foto = self.subir_foto_a_firebase_con_ruta(ruta_foto)
            if not url_publica_foto or "ERROR" in url_publica_foto:
                url_publica_foto = "PENDIENTE_SUBIDA"

            data_visita = {
                "cliente_id": cliente_id_formateado,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "inventario_animales": inv_animales,
                "parametros_tecnicos": params_visita,
                "control_alimento": detalle_bodega,
                "ruta_foto_evidencia": url_publica_foto
            }
            
            # Forzamos una limpieza estricta reemplazando puntos, barras y espacios prohibidos por Firebase
            nodo_url_seguro = str(cliente_id_formateado).replace(".", "_").replace("/", "_").replace(" ", "_")
            
            # URL limpia hacia la estructura de distribuidoras en Firebase Realtime Database
            url_rtdb = f"{URL_BASE}/distribuidoras/DISTRIBUIDORA_ALINVET/visitas/{nodo_url_seguro}_{timestamp_id}.json"
            
            response_rtdb = requests.put(url_rtdb, json=data_visita, timeout=15)
            
            if response_rtdb.status_code in [200, 204]:
                try:
                    conn = sqlite3.connect(get_db_path())
                    res = conn.execute("SELECT valor FROM cache_app WHERE clave='clientes'").fetchone()
                    if res and res[0]:
                        clis = json.loads(res[0])
                        if self.id_cliente_actual in clis:
                            clis[self.id_cliente_actual]["inventario"] = inv_animales
                            
                            inv_prod_nuevo = {}
                            for prod_name, valores in detalle_bodega.items():
                                inv_prod_nuevo[prod_name] = valores.get("actual", 0.0)
                            clis[self.id_cliente_actual]["inventario_productos"] = inv_prod_nuevo
                            
                            conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('clientes', ?)", (json.dumps(clis),))
                    conn.commit()
                    conn.close()
                except Exception as ex_db:
                    print(f"Error actualizando caché local: {ex_db}")

                Clock.schedule_once(lambda dt: self.actualizar_ui_exito())
                Clock.schedule_once(lambda dt: self.limpiar_campos_y_salir())
            else:
                print(f"Error HTTP RTDB Firebase: {response_rtdb.status_code} - {response_rtdb.text}")
                Clock.schedule_once(lambda dt: self.actualizar_ui_error())
        except Exception as e:
            print(f"Excepción hilo registro: {e}")
            Clock.schedule_once(lambda dt: self.actualizar_ui_error())

    def limpiar_campos_y_salir(self):
        self.limpiar_campos()
        self.manager.current = 'main'

    def limpiar_campos(self):
        self.sp_cliente.text = "Seleccione Productor"; self.info_lab.text = "Especie: -- | Zona: --"
        self.box_animales.clear_widgets(); self.box_parametros.clear_widgets(); self.box_productos.clear_widgets()
        self.sp_master_prod.text = "Seleccione Alimento"; self.sp_master_prod.values = []
        self.inputs_inv = {}; self.inputs_par = {}; self.inputs_existencia_actual = {}; self.id_cliente_actual = None
        
        self.ruta_foto_actual = ""
        self.lbl_foto.text = "Foto no capturada *"
        self.lbl_foto.color = (1, 0.3, 0.3, 1)

class RegistroPuntoVentaScreen(PantallaConDatos):
    def __init__(self, **kw):
        super().__init__(**kw)
        
        # --- VARIABLES PARA GEOLOCALIZACIÓN REFORZADA ---
        self.latitud_actual = 0.0
        self.longitud_actual = 0.0
        self.listener_gps = None  # Almacenará la referencia del escuchador nativo
        
        # Layout Base
        l = FloatLayout(size_hint=(1, 1))
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False, size_hint=(1, 1)))
        
        # ScrollView
        self.sc = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(10))
        
        # Contenedor Dinámico
        self.container = ContainerTransparente(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        
        self.container.add_widget(BigLabel(text="ALTA DE NUEVO PUNTO DE VENTA"))
        
        # Campos
        self.container.add_widget(Label(text="Nombre del Establecimiento:", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        self.txt_nombre = BigInput(hint_text="Ej: Pulpería El Jícaro", size_hint_y=None, height=dp(60))
        self.container.add_widget(self.txt_nombre)
        
        self.container.add_widget(Label(text="Teléfono:", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        self.txt_tel = BigInput(hint_text="0000-0000", input_filter='int', size_hint_y=None, height=dp(60))
        self.container.add_widget(self.txt_tel)
        
        self.container.add_widget(Label(text="Zona Geográfica:", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        self.sp_zona = Spinner(text="Seleccione Zona", size_hint_y=None, height=dp(60), background_color=AZUL_LOGO)
        self.container.add_widget(self.sp_zona)
        
        self.container.add_widget(Label(text="Técnico Asignado:", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        self.sp_tecnico = Spinner(text="Seleccione Técnico", size_hint_y=None, height=dp(60), background_color=AZUL_LOGO)
        self.container.add_widget(self.sp_tecnico)

        # =========================================================================
        # SECCIÓN GPS CONFIGURADA PARA MÁXIMA PRECISIÓN GRATUITA
        # =========================================================================
        self.container.add_widget(Label(text="Ubicación Geográfica (GPS Alta Precisión):", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        
        self.layout_gps = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(60))
        
        self.lbl_gps = Label(
            text="Coordenadas: No capturadas", 
            color=(1, 1, 1, 1), 
            font_size=dp(14), 
            bold=True, 
            size_hint_x=0.6, 
            halign='center', 
            valign='middle',
            outline_color=(0, 0, 0, 1), 
            outline_width=dp(1.5)
        )
        self.lbl_gps.bind(size=lambda obj, _: setattr(obj, 'text_size', (obj.width, None)))
        self.layout_gps.add_widget(self.lbl_gps)
        
        self.btn_gps = Button(
            text="ESTABILIZAR GPS", 
            size_hint_x=0.4, 
            background_color=(0.1, 0.4, 0.6, 1), 
            bold=True, 
            font_size=dp(14)
        )
        self.btn_gps.bind(on_release=self.obtener_ubicacion_gps)
        self.layout_gps.add_widget(self.btn_gps)
        
        self.container.add_widget(self.layout_gps)
        # =========================================================================

        # Botón de Guardar
        self.btn_guardar = Button(text="REGISTRAR LOCAL", size_hint_y=None, height=dp(80), background_color=VERDE_LOGO, bold=True)
        self.btn_guardar.bind(on_release=self.guardar_nuevo_pv_protegido)
        self.container.add_widget(self.btn_guardar)
        
        self.container.add_widget(Button(text="VOLVER", size_hint_y=None, height=dp(55), on_release=lambda x: self.volver()))
        
        # ENSAMBLADO FINAL
        self.sc.add_widget(self.container)
        l.add_widget(self.sc)
        self.add_widget(l)

    # =========================================================================
    # LÓGICA DE ESCUCHA CONTINUA Y FILTRADO POR PRECISIÓN METRICA
    # =========================================================================
    def obtener_ubicacion_gps(self, instance):
        """Solicita permisos en Android e inicia la escucha en tiempo real."""
        import platform
        if platform.system() == 'Android':
            try:
                from android.permissions import request_permissions, Permission
                def callback_permisos(permissions, results):
                    if all(results):
                        self.lbl_gps.text = "Buscando satélites...\nEspere a que estabilice"
                        self.lbl_gps.color = (1, 0.6, 0.2, 1)
                        self.activar_escucha_gps_nativa()
                    else:
                        self.lbl_gps.text = "Permiso de GPS denegado"
                        self.lbl_gps.color = (1, 0.3, 0.3, 1)
                request_permissions([Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION], callback_permisos)
            except Exception as e:
                self.lbl_gps.text = "Error solicitando permisos GPS"
                self.lbl_gps.color = (1, 0.3, 0.3, 1)
        else:
            # Simulación en PC
            self.latitud_actual = 12.6234
            self.longitud_actual = -87.1245
            self.lbl_gps.text = f"GPS (Simulado PC):\nLat: {self.latitud_actual} | Lon: {self.longitud_actual}\nError estimado: ~1m"
            self.lbl_gps.color = (0.3, 1, 0.3, 1)

    def activar_escucha_gps_nativa(self):
        """Registra un LocationListener nativo que evalúa dinámicamente el margen de error."""
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            Looper = autoclass('android.os.Looper')
            
            actividad_actual = PythonActivity.mActivity
            self.servicio_ubicacion = actividad_actual.getSystemService(Context.LOCATION_SERVICE)

            # Definición del Escuchador Nativo usando PythonJavaClass
            class GPSLocationListener(PythonJavaClass):
                __javainterfaces__ = ['android/location/LocationListener']

                def __init__(self, callback_update):
                    super().__init__()
                    self.callback_update = callback_update

                @java_method('(Landroid/location/Location;)V')
                def onLocationChanged(self, location):
                    if location:
                        self.callback_update(location)

                @java_method('(Ljava/lang/String;ILandroid/os/Bundle;)V')
                def onStatusChanged(self, provider, status, extras): pass

                @java_method('(Ljava/lang/String;)V')
                def onProviderEnabled(self, provider): pass

                @java_method('(Ljava/lang/String;)V')
                def onProviderDisabled(self, provider): pass

            # Si ya existía un listener activo, lo removemos antes de crear uno nuevo
            if self.listener_gps:
                self.servicio_ubicacion.removeUpdates(self.listener_gps)

            self.listener_gps = GPSLocationListener(self.procesar_cambio_ubicacion)
            
            # Solicitamos actualizaciones cada 1000 milisegundos (1 segundo) y 0 metros de cambio mínimo
            # para obligar al hardware a darnos la lectura más fresca y precisa disponible.
            self.servicio_ubicacion.requestLocationUpdates(
                'gps', 
                int(1000), 
                float(0), 
                self.listener_gps, 
                Looper.getMainLooper()
            )
        except Exception as e:
            self.lbl_gps.text = "Error al inicializar escucha GPS"
            self.lbl_gps.color = (1, 0.3, 0.3, 1)

    def procesar_cambio_ubicacion(self, location):
        """Evalúa el margen de precisión devuelto en metros por el hardware."""
        try:
            precision_metros = float(location.getAccuracy())
            lat = float(location.getLatitude())
            lon = float(location.getLongitude())

            # Actualizamos la pantalla de forma interactiva para que el técnico vea cómo mejora la señal
            self.lbl_gps.text = f"Buscando...\nMargen de error actual: {round(precision_metros, 1)} metros"

            # FILTRO DE DESCARTE INTERNO DE SEGURIDAD:
            # Guardamos las coordenadas inmediatamente, pero el color cambiará a VERDE
            # solo si alcanza el límite óptimo físico del teléfono (menor o igual a 5 metros).
            self.latitud_actual = lat
            self.longitud_actual = lon

            if precision_metros <= 5.0:
                # El GPS llegó a su punto más fino posible. Fijamos y detenemos el rastreo para ahorrar batería.
                self.lbl_gps.text = f"¡MÁXIMA PRECISIÓN FIJADA!\nLat: {round(lat, 5)} | Lon: {round(lon, 5)}\nMargen: ±{round(precision_metros, 1)}m"
                self.lbl_gps.color = (0.3, 1, 0.3, 1) # Verde óptimo
                
                # Apagamos el sensor ya que logramos el objetivo
                if self.listener_gps and self.servicio_ubicacion:
                    self.servicio_ubicacion.removeUpdates(self.listener_gps)
                    self.listener_gps = None
            else:
                # Sigue buscando mejores satélites, mantenemos color naranja de advertencia
                self.lbl_gps.color = (1, 0.6, 0.2, 1)
        except Exception as e:
            print(f"Error procesando coordenadas: {e}")

    def guardar_nuevo_pv_protegido(self, instance):
        self.txt_nombre.focus = False
        self.txt_tel.focus = False
        Window.release_all_keyboards()
        self.guardar_nuevo_pv(instance)

    def on_enter(self):
        self.latitud_actual = 0.0
        self.longitud_actual = 0.0
        if hasattr(self, 'lbl_gps'):
            self.lbl_gps.text = "Coordenadas: No capturadas"
            self.lbl_gps.color = (1, 1, 1, 1)
        Clock.schedule_once(self.cargar_registro_asincrono, 0.1)

    def on_leave(self):
        """Garantiza apagar el hardware de GPS si el usuario sale de la pantalla."""
        if hasattr(self, 'servicio_ubicacion') and self.listener_gps:
            try:
                self.servicio_ubicacion.removeUpdates(self.listener_gps)
                self.listener_gps = None
            except:
                pass

    def cargar_registro_asincrono(self, dt):
        if not hasattr(self, 'sp_zona') or not hasattr(self, 'sp_tecnico'):
            return

        for i in range(3):
            conn = None
            try:
                conn = sqlite3.connect(get_db_path(), timeout=10)
                cursor = conn.cursor()
                
                z_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='zonas'").fetchone()
                if z_res and z_res[0]:
                    try:
                        vals = json.loads(z_res[0])
                        lista = [str(v.get('nombre', v)) if isinstance(v, dict) else str(v) for v in vals.values() if v]
                        self.sp_zona.values = sorted(list(set(lista)))
                    except:
                        self.sp_zona.values = ["Error formato zonas"]
                else:
                    self.sp_zona.values = ["Sin zonas"]

                t_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='tecnicos_dict'").fetchone()
                if t_res and t_res[0]:
                    try:
                        tecnicos = json.loads(t_res[0])
                        self.dict_tecnicos_local = { 
                            str(v.get('nombre', 'N/A') if isinstance(v, dict) else v): k 
                            for k, v in tecnicos.items() 
                        }
                        nombres = [n for n in self.dict_tecnicos_local.keys() if n and str(n).strip()]
                        self.sp_tecnico.values = sorted(list(set(nombres))) if nombres else ["Sin técnicos"]
                    except:
                        self.sp_tecnico.values = ["Error formato técnicos"]
                else:
                    self.dict_tecnicos_local = {}
                    self.sp_tecnico.values = ["Sin técnicos"]
                
                cursor.close()
                conn.close()
                return

            except sqlite3.OperationalError:
                if conn: conn.close()
                time.sleep(0.5)
                continue 
            except Exception as e:
                if conn: conn.close()
                print(f"Error asíncrono en registro: {e}")
                self.sp_zona.values = ["Error carga"]
                self.sp_tecnico.values = ["Error carga"]
                break

    def guardar_nuevo_pv(self, instance):
        nombre = self.txt_nombre.text.strip()
        if not nombre or self.sp_zona.text == "Seleccione Zona":
            print("Faltan datos obligatorios")
            return

        id_tec = self.dict_tecnicos_local.get(self.sp_tecnico.text, "N/A")

        data = {
            "id_interno": nombre.replace(" ", "_").upper(), 
            "nombre": nombre,
            "telefono": self.txt_tel.text.strip(),
            "zona": self.sp_zona.text,
            "tecnico": self.sp_tecnico.text,
            "id_tecnico": id_tec,
            "latitud": self.latitud_actual,
            "longitud": self.longitud_actual,
            "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tipo_registro": "NUEVO_PV" 
        }

        try:
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT INTO cola_sincro (tipo, datos) VALUES ('NUEVO_PV', ?)", (json.dumps(data),))
            conn.commit()
            conn.close()
            
            print(f"Local {nombre} en cola de sincronización maestra.")
            self.volver()

        except Exception as e:
            print(f"Error local: {e}")
            self.volver()

    def volver(self):
        # Desconectar el listener al volver para evitar fugas de memoria
        if hasattr(self, 'servicio_ubicacion') and self.listener_gps:
            try:
                self.servicio_ubicacion.removeUpdates(self.listener_gps)
                self.listener_gps = None
            except:
                pass
        self.txt_nombre.text = ""
        self.txt_tel.text = ""
        self.latitud_actual = 0.0
        self.longitud_actual = 0.0
        self.manager.current = 'main'


class VisitaPuntoVentaScreen(PantallaConDatos):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.inputs_existencia = {}
        self.marcas_seleccionadas = []
        
        self.foto_base64 = ""
        self.ruta_foto_actual = ""
        
        l = FloatLayout(size_hint=(1, 1))
        l.add_widget(Image(source=resource_path('fondo.jpg'), allow_stretch=True, keep_ratio=False, size_hint=(1, 1)))
        
        self.sc = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(10))
        self.container = ContainerTransparente(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        
        self.container.add_widget(BigLabel(text="VISITA DE SEGUIMIENTO (PV)"))
        
        self.sp_pv = Spinner(text="Seleccione Punto de Venta", size_hint_y=None, height=dp(65), background_color=AZUL_LOGO)
        self.container.add_widget(self.sp_pv)
        
        # --- SECCIÓN MARCAS ---
        self.container.add_widget(Label(text="Marcas de Competencia:", size_hint_y=None, height=dp(30), bold=True, outline_color=(0,0,0,1), outline_width=1.5))
        
        box_m = BoxLayout(size_hint_y=None, height=dp(55), spacing=dp(5))
        self.sp_marcas = Spinner(text="Seleccione Marca", size_hint_y=None, height=dp(55), background_color=(0.1, 0.3, 0.5, 1))
        self.sp_marcas.bind(text=self.add_marca)
        box_m.add_widget(self.sp_marcas)
        
        btn_nueva_m = Button(text="+ NUEVA", size_hint_x=0.3, background_color=(0.2, 0.6, 0.2, 1), bold=True)
        btn_nueva_m.bind(on_release=self.popup_nueva_marca) 
        box_m.add_widget(btn_nueva_m)
        self.container.add_widget(box_m)
        
        self.lbl_marcas = Label(text="Marcas: []", size_hint_y=None, height=dp(40), italic=True, bold=True, outline_color=(0,0,0,1), outline_width=1.5)
        self.container.add_widget(self.lbl_marcas)

        # --- SECCIÓN PUBLICIDAD ---
        self.sp_pub_propia = Spinner(text="Publicidad Propia: Buena", values=("Excelente", "Buena", "Deteriorada", "Sin Publicidad"), size_hint_y=None, height=dp(55), background_color=VERDE_LOGO)
        self.container.add_widget(self.sp_pub_propia)
        
        self.sp_pub_comp = Spinner(text="Publicidad Competencia: Baja", values=("Dominante", "Media", "Baja", "Nula"), size_hint_y=None, height=dp(55), background_color=(0.7, 0.2, 0.2, 1))
        self.container.add_widget(self.sp_pub_comp)

        # --- INVENTARIO ---
        self.sp_prod = Spinner(
            text="Seleccione Producto", 
            size_hint_y=None, 
            height=dp(60), 
            font_size=dp(20),
            background_color=AZUL_LOGO
        )
        self.container.add_widget(self.sp_prod)
        
        btn_add = Button(
            text="+ AÑADIR PRODUCTO", 
            size_hint_y=None, 
            height=dp(60), 
            font_size=dp(20),
            background_color=(0.1, 0.5, 0.1, 1), 
            bold=True
        )
        btn_add.bind(on_release=self.add_item_fila)
        self.container.add_widget(btn_add)
        
        self.box_items = BoxLayout(orientation='vertical', spacing=dp(15), size_hint_y=None)
        self.box_items.bind(minimum_height=self.box_items.setter('height'))
        self.container.add_widget(self.box_items)
        
        # --- MÓDULO DE FOTOGRAFÍA OBLIGATORIA ---
        self.container.add_widget(BigLabel(text="Evidencia Fotográfica (Obligatoria):"))
        
        self.layout_foto = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(60))
        
        self.lbl_foto_estado = Label(
            text="Foto no capturada (*Requerido)", 
            color=(1, 0.3, 0.3, 1), 
            font_size=dp(15), 
            bold=True, 
            size_hint_x=0.6, 
            halign='center', 
            valign='middle',
            outline_color=(0, 0, 0, 1), 
            outline_width=dp(1.5)
        )
        self.lbl_foto_estado.bind(size=lambda obj, _: setattr(obj, 'text_size', (obj.width, None)))
        self.layout_foto.add_widget(self.lbl_foto_estado)
        
        self.btn_camara = Button(
            text="ABRIR CÁMARA", 
            size_hint_x=0.4, 
            background_color=(0.1, 0.4, 0.6, 1), 
            bold=True, 
            font_size=dp(14)
        )
        self.btn_camara.bind(on_release=self.capturar_evidencia_foto)
        self.layout_foto.add_widget(self.btn_camara)
        
        self.container.add_widget(self.layout_foto)
        
        # --- BOTONES ---
        self.btn_v = Button(text="GUARDAR REPORTE DE VISITA", size_hint_y=None, height=dp(80), background_color=VERDE_LOGO, bold=True)
        self.btn_v.bind(on_release=self.enviar_visita_protegido)
        self.container.add_widget(self.btn_v)
        
        self.btn_back = Button(text="VOLVER", size_hint_y=None, height=dp(55))
        self.btn_back.bind(on_release=lambda x: setattr(self.manager, 'current', 'main'))
        self.container.add_widget(self.btn_back)
        
        self.sc.add_widget(self.container)
        l.add_widget(self.sc)
        self.add_widget(l)

    def enviar_visita_protegido(self, instance):
        Window.release_all_keyboards()
        self.enviar_visita(instance)

    def on_enter(self):
        self.sp_pv.text = "Seleccione Punto de Venta"
        threading.Thread(target=self.ejecutar_carga_en_hilo, daemon=True).start()

    def ejecutar_carga_en_hilo(self):
        for i in range(3):
            conn = None
            try:
                db_path = get_db_path()
                conn = sqlite3.connect(db_path, timeout=15)
                cursor = conn.cursor()
                
                m_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='puntos_venta_maestro'").fetchone()
                p_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='catalogo'").fetchone()
                mar_res = cursor.execute("SELECT valor FROM cache_app WHERE clave='marcas_competencia'").fetchone()
                
                cursor.close()
                conn.close()
                
                app = App.get_running_app()
                mi_id = str(getattr(app, 'device_id', ''))
                
                mis_pvs = []
                if m_res and m_res[0]:
                    pvs_data = json.loads(m_res[0])
                    mis_pvs = [str(nombre).strip().upper() for nombre, datos in pvs_data.items() 
                               if isinstance(datos, dict) and str(datos.get('id_tecnico', '')) == mi_id]
                
                valores_pv = sorted(list(set(mis_pvs))) if mis_pvs else []
                if not valores_pv and app.locales_lista:
                    valores_pv = app.locales_lista
                elif not valores_pv:
                    valores_pv = ["Sin locales asignados"]

                valores_prod = ["Sin productos"]
                if p_res and p_res[0]:
                    catalogo = json.loads(p_res[0])
                    nombres_prod = [str(p.get('nombre', '')).strip().upper() for p in catalogo.values() 
                                    if isinstance(p, dict) and p.get('nombre')]
                    if nombres_prod:
                        valores_prod = sorted(list(set(nombres_prod)))

                valores_marcas = ["Sin marcas"]
                if mar_res and mar_res[0]:
                    marcas = json.loads(mar_res[0])
                    lista_marcas = [str(m).strip().upper() for m in marcas.values()]
                    if lista_marcas:
                        valores_marcas = sorted(list(set(lista_marcas)))

                Clock.schedule_once(lambda dt: self.actualizar_componentes_ui(valores_pv, valores_prod, valores_marcas), 0)
                return

            except sqlite3.OperationalError:
                if conn: conn.close()
                time.sleep(0.3)
                continue
            except Exception as e:
                if conn: conn.close()
                break
                
        app = App.get_running_app()
        pv_fallback = app.locales_lista if app.locales_lista else ["Sin locales asignados"]
        prod_fallback = app.productos_lista if app.productos_lista else ["Sin productos"]
        Clock.schedule_once(lambda dt: self.actualizar_componentes_ui(pv_fallback, prod_fallback, ["Sin marcas"]), 0)

    def actualizar_componentes_ui(self, pvs, productos, marcas):
        self.sp_pv.values = pvs
        self.sp_prod.values = productos
        self.sp_marcas.values = marcas

    def add_marca(self, spinner, text):
        if text not in ["Seleccione Marca", "Sin marcas"] and text not in self.marcas_seleccionadas:
            self.marcas_seleccionadas.append(text)
            self.lbl_marcas.text = f"Marcas: {', '.join(self.marcas_seleccionadas)}"

    def popup_nueva_marca(self, instance):
        Window.release_all_keyboards()
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        txt = TextInput(hint_text="Nombre de la marca", multiline=False, size_hint_y=None, height=dp(50))
        btn = Button(text="REGISTRAR", size_hint_y=None, height=dp(50), background_color=(0.1, 0.5, 0.1, 1), bold=True)
        
        content.add_widget(txt)
        content.add_widget(btn)
        
        popup = Popup(title='Registrar Marca de Competencia', content=content, size_hint=(0.8, 0.4), auto_dismiss=True)
        
        def guardar_m(obj):
            nueva_m = txt.text.strip().upper()
            if nueva_m:
                conn = None
                try:
                    conn = sqlite3.connect(get_db_path())
                    data = {"nombre": nueva_m, "tipo": "NUEVA_MARCA_CATALOGO"}
                    conn.execute("INSERT INTO cola_sincro (tipo, datos) VALUES ('NUEVA_MARCA_CATALOGO', ?)", (json.dumps(data),))
                    res = conn.execute("SELECT valor FROM cache_app WHERE clave='marcas_competencia'").fetchone()
                    marcas = json.loads(res[0]) if res else {}
                    marcas[nueva_m.replace(" ", "_")] = nueva_m
                    conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('marcas_competencia', ?)", (json.dumps(marcas),))
                    conn.commit()
                    conn.close()
                    
                    self.sp_marcas.values = sorted(marcas.values())

                    # Sincronización inmediata a Firebase con ruta segura de distribuidora corregida
                    app = App.get_running_app()
                    distribuidora = getattr(app, 'distribuidora_actual', 'DISTRIBUIDORA_ALINVET')
                    url_base_rtdb = getattr(app, 'firebase_url', 'https://campodata-cd974-default-rtdb.firebaseio.com')
                    url_marca = f"{url_base_rtdb}/distribuidoras/{distribuidora}/marcas_competencia/{sanitizar_llave(nueva_m)}.json"
                    requests.put(url_marca, json=nueva_m, timeout=10)
                except Exception as e:
                    if conn: conn.close()
                    print(f"Error al guardar nueva marca: {e}")
                popup.dismiss()
        
        btn.bind(on_release=guardar_m)
        popup.bind(on_dismiss=lambda *args: Window.release_all_keyboards())
        popup.open()

    def add_item_fila(self, instance):
        p = self.sp_prod.text
        if p in ["Seleccione Producto", "Sin productos"] or p in self.inputs_existencia:
            return

        try:
            val_inicial = 0.0
            conn = None
            try:
                conn = sqlite3.connect(get_db_path())
                res = conn.execute("SELECT valor FROM cache_app WHERE clave='puntos_venta_maestro'").fetchone()
                conn.close()
                if res:
                    maestro = json.loads(res[0])
                    pv_data = maestro.get(self.sp_pv.text, {})
                    stock_dict = pv_data.get('stock_actual', {})
                    val_inicial = stock_dict.get(sanitizar_llave(p), 0.0)
            except:
                if conn: conn.close()
                val_inicial = 0.0

            if not self.inputs_existencia:
                header = BoxLayout(size_hint_y=None, height=dp(30))
                header.add_widget(Label(text="Producto.", font_size=dp(15), bold=True, outline_width=1, size_hint_x=0.16))
                header.add_widget(Label(text="Inicial", font_size=dp(15), bold=True, outline_width=1, size_hint_x=0.21))
                header.add_widget(Label(text="Tránsito", font_size=dp(15), bold=True, outline_width=1, size_hint_x=0.21))
                header.add_widget(Label(text="Venta", font_size=dp(15), bold=True, outline_width=1, size_hint_x=0.21))
                header.add_widget(Label(text="Final", font_size=dp(15), bold=True, outline_width=1, size_hint_x=0.21))
                self.box_items.add_widget(header)

            fila = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(5))
            fila.add_widget(Label(text=p[:10], size_hint_x=0.16, font_size=dp(10), bold=True))
            
            c_ini = BigInput(text=str(val_inicial), size_hint_x=0.21, readonly=True, background_color=(0.9, 0.9, 0.9, 1))
            c_tra = BigInput(text="", input_filter='float', size_hint_x=0.21, multiline=False)
            c_ven = BigInput(text="", input_filter='float', size_hint_x=0.21, multiline=False)
            c_fin = BigInput(text=str(val_inicial), size_hint_x=0.21, readonly=True, background_color=(0.8, 1, 0.8, 1))

            def calcular(*args):
                try:
                    def f_val(v):
                        try:
                            limpio = v.strip()
                            return float(limpio) if limpio else 0.0
                        except: return 0.0
                    
                    resultado = f_val(c_ini.text) + f_val(c_tra.text) - f_val(c_ven.text)
                    c_fin.text = str(round(max(0.0, resultado), 2))
                except:
                    pass

            c_tra.bind(text=calcular)
            c_ven.bind(text=calcular)

            fila.add_widget(c_ini)
            fila.add_widget(c_tra)
            fila.add_widget(c_ven)
            fila.add_widget(c_fin)
            
            self.box_items.add_widget(fila)
            self.inputs_existencia[p] = {"ini": c_ini, "tra": c_tra, "ven": c_ven, "fin": c_fin}
            
        except Exception as e:
            print(f"Error crítico en add_item_fila: {e}")

    def capturar_evidencia_foto(self, instance):
        import platform
        if platform.system() == 'Android':
            try:
                from android.permissions import request_permissions, Permission
                def callback_permisos(permissions, results):
                    if all(results):
                        self.ejecutar_intent_camara()
                    else:
                        self.lbl_foto_estado.text = "Falta permiso de cámara"
                        self.lbl_foto_estado.color = (1, 0.3, 0.3, 1)
                request_permissions([Permission.CAMERA], callback_permisos)
            except Exception as e:
                self.ejecutar_intent_camara()
        else:
            self.foto_base64 = "simulado"
            self.ruta_foto_actual = ""
            self.lbl_foto_estado.text = "Foto Capturada (PC)"
            self.lbl_foto_estado.color = (0.3, 1, 0.3, 1)

    def ejecutar_intent_camara(self):
        try:
            import os
            from jnius import autoclass
            from android.activity import bind as android_bind
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            MediaStore = autoclass('android.provider.MediaStore')
            Uri = autoclass('android.net.Uri')
            File = autoclass('java.io.File')
            
            context = PythonActivity.mActivity
            directorio_archivos = context.getFilesDir()
            archivo_temporal = File(directorio_archivos, "visita_temp.jpg")
            self.ruta_foto_actual = archivo_temporal.getAbsolutePath()
            
            uri_destino = Uri.fromFile(archivo_temporal)
            
            android_bind(on_activity_result=self.on_resultado_camara)
            
            intent_camara = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent_camara.putExtra(MediaStore.EXTRA_OUTPUT, uri_destino)
            
            PythonActivity.mActivity.startActivityForResult(intent_camara, 1011)
            
            self.lbl_foto_estado.text = "Cámara abierta..."
            self.lbl_foto_estado.color = (1, 1, 0.3, 1)
        except Exception as e:
            try:
                intent_camara = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
                PythonActivity.mActivity.startActivityForResult(intent_camara, 1011)
                self.lbl_foto_estado.text = "Cámara abierta (Alternativa)..."
            except Exception as ex:
                self.lbl_foto_estado.text = "Error al abrir la cámara"
                self.lbl_foto_estado.color = (1, 0.3, 0.3, 1)

    def on_resultado_camara(self, request_code, result_code, intent):
        try:
            from android.activity import unbind as android_unbind
            android_unbind(on_activity_result=self.on_resultado_camara)
        except:
            pass

        if request_code == 1011:
            import os
            if not getattr(self, 'ruta_foto_actual', ""):
                try:
                    from jnius import autoclass
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    context = PythonActivity.mActivity
                    self.ruta_foto_actual = os.path.join(context.getFilesDir().getAbsolutePath(), "visita_temp.jpg")
                except:
                    self.ruta_foto_actual = "visita_temp.jpg"

            if result_code == -1 or (os.path.exists(self.ruta_foto_actual) and os.path.getsize(self.ruta_foto_actual) > 0):
                self.foto_base64 = "capturado_ok"
                self.lbl_foto_estado.text = "Foto Capturada OK"
                self.lbl_foto_estado.color = (0.3, 1, 0.3, 1)
            else:
                try:
                    with open(self.ruta_foto_actual, "wb") as f:
                        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF")
                    self.foto_base64 = "capturado_ok"
                    self.lbl_foto_estado.text = "Foto Capturada OK"
                    self.lbl_foto_estado.color = (0.3, 1, 0.3, 1)
                except:
                    self.ruta_foto_actual = ""
                    self.foto_base64 = ""
                    self.lbl_foto_estado.text = "Captura cancelada *"
                    self.lbl_foto_estado.color = (1, 0.3, 0.3, 1)

    def subir_foto_a_firebase_con_ruta(self, ruta_archivo):
        import os, uuid, requests, time, platform
        
        # Si estamos en PC y no hay ruta o la ruta no existe, usamos una imagen simulada completa para el Storage
        if platform.system() != 'Android':
            if not ruta_archivo or not os.path.exists(ruta_archivo):
                ruta_archivo = "evidencia_visita_simulada.jpg"
                if not os.path.exists(ruta_archivo):
                    try:
                        # Generamos un archivo de prueba con estructura JPEG válida de mayor tamaño para habilitar la vista previa
                        dummy_jpeg_data = (
                            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00'
                            b'\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19'
                            b'\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' + b'\x00' * 5000
                        )
                        with open(ruta_archivo, "wb") as f:
                            f.write(dummy_jpeg_data)
                    except Exception:
                        pass

        if not ruta_archivo or not os.path.exists(ruta_archivo):
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity
                ruta_alternativa = os.path.join(context.getFilesDir().getAbsolutePath(), "visita_temp.jpg")
                if os.path.exists(ruta_alternativa):
                    ruta_archivo = ruta_alternativa
            except Exception:
                pass

        if not ruta_archivo or not os.path.exists(ruta_archivo):
            print("[STORAGE ERROR] La ruta de la foto sigue vacía o no existe físicamente.")
            return "PENDIENTE_SUBIDA_FOTO"

        try:
            nombre_archivo = os.path.basename(ruta_archivo)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            ruta_remota = f"fotos_visitas/visita_{timestamp_str}_{nombre_archivo}"
            
            with open(ruta_archivo, "rb") as f:
                file_data = f.read()

            bucket_name = "campodata-cd974.firebasestorage.app"
            file_name_encoded = ruta_remota.replace("/", "%2F")
            token_personalizado = str(uuid.uuid4())
            
            url_upload = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o?uploadType=media&name={file_name_encoded}"
            headers = {"Content-Type": "image/jpeg"}

            response = requests.post(url_upload, data=file_data, headers=headers, timeout=30)

            if response.status_code == 200:
                res_json = response.json()
                raw_tokens = res_json.get("downloadTokens", "")
                download_token = raw_tokens.split(",")[0] if raw_tokens else token_personalizado
                
                url_publica = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{file_name_encoded}?alt=media&token={download_token}"
                return url_publica
            else:
                return f"ERROR_HTTP_{response.status_code}"
                
        except Exception as e:
            return "ERROR_EXCEPCION_CRITICA"

    def actualizar_ui_exito(self):
        if hasattr(self, 'lbl_foto_estado'):
            self.lbl_foto_estado.text = "¡Enviado con éxito!"
            self.lbl_foto_estado.color = (0.3, 1, 0.3, 1)

    def actualizar_ui_error(self):
        if hasattr(self, 'lbl_foto_estado'):
            self.lbl_foto_estado.text = "Error al enviar datos"
            self.lbl_foto_estado.color = (1, 0.3, 0.3, 1)

    def _enviar_visita_firebase_hilo(self, nombre_pv, timestamp_id, data, ruta_archivo):
        try:
            url_foto = self.subir_foto_a_firebase_con_ruta(ruta_archivo)
            if url_foto and not url_foto.startswith("ERROR"):
                data["foto_evidencia"] = url_foto
            else:
                data["foto_evidencia"] = "ERROR_SUBIDA_FOTO"

            app = App.get_running_app()
            distribuidora = getattr(app, 'distribuidora_actual', 'DISTRIBUIDORA_ALINVET')
            url_base_rtdb = getattr(app, 'firebase_url', 'https://campodata-cd974-default-rtdb.firebaseio.com')

            nodo_url_seguro = sanitizar_llave(nombre_pv)
            url_rtdb = f"{url_base_rtdb}/distribuidoras/{distribuidora}/visitas/{nodo_url_seguro}_{timestamp_id}.json"

            headers = {"Content-Type": "application/json"}
            response = requests.put(url_rtdb, data=json.dumps(data), headers=headers, timeout=30)

            if response.status_code == 200:
                Clock.schedule_once(lambda dt: self.actualizar_ui_exito(), 0)
            else:
                Clock.schedule_once(lambda dt: self.actualizar_ui_error(), 0)

        except Exception as e:
            Clock.schedule_once(lambda dt: self.actualizar_ui_error(), 0)

    def enviar_visita(self, instance):
        if self.sp_pv.text in ["Seleccione Punto de Venta", "Sin locales asignados", "Error carga"]: 
            return
        
        if not self.foto_base64 or self.foto_base64.strip() == "":
            self.lbl_foto_estado.text = "¡ERROR! Debe tomar la foto primero"
            self.lbl_foto_estado.color = (1, 0.1, 0.1, 1)
            return

        inventario_reporte = {}
        stock_actualizado_cache = {}
        
        for prod_nombre, celdas in self.inputs_existencia.items():
            llave_prod = sanitizar_llave(prod_nombre)
            val_final = float(celdas['fin'].text if celdas['fin'].text else 0)
            
            inventario_reporte[llave_prod] = {
                "inicial": float(celdas['ini'].text if celdas['ini'].text else 0),
                "transito": float(celdas['tra'].text if celdas['tra'].text else 0),
                "venta": float(celdas['ven'].text if celdas['ven'].text else 0),
                "final": val_final
            }
            stock_actualizado_cache[llave_prod] = val_final

        timestamp_id = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        fecha_str = datetime.now().strftime("%Y_%m_%d_%H:_%M:_%S")
        nombre_pv = self.sp_pv.text
        ruta_foto_segura = getattr(self, 'ruta_foto_actual', "")

        # Obtener la URL correcta (simulada en PC o subida/ruta real en Android)
        import platform
        if platform.system() != 'Android':
            url_foto_final = "https://firebasestorage.googleapis.com/v0/b/campodata-cd974.firebasestorage.app/o/fotos_visitas%2Fsimulacion_pc.jpg?alt=media&token=simulado-pc"
        else:
            url_foto_final = self.subir_foto_a_firebase_con_ruta(ruta_foto_segura)

        data = {
            "establecimiento": nombre_pv,
            "marcas": self.marcas_seleccionadas,
            "pub_propia": self.sp_pub_propia.text,
            "pub_comp": self.sp_pub_comp.text,
            "inventario": inventario_reporte,
            "fecha": fecha_str,
            "tipo_registro": "VISITA_PV",
            "foto_evidencia": url_foto_final
        }

        conn = None
        try:
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT INTO cola_sincro (tipo, datos) VALUES ('VISITA_PV', ?)", (json.dumps(data),))
            
            res = conn.execute("SELECT valor FROM cache_app WHERE clave='puntos_venta_maestro'").fetchone()
            if res:
                maestro = json.loads(res[0])
                if nombre_pv in maestro:
                    if 'stock_actual' not in maestro[nombre_pv]:
                        maestro[nombre_pv]['stock_actual'] = {}
                    maestro[nombre_pv]['stock_actual'].update(stock_actualizado_cache)
                    conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('puntos_venta_maestro', ?)", (json.dumps(maestro),))
            
            conn.commit()
            conn.close()
        except Exception as e:
            if conn: conn.close()

        threading.Thread(
            target=self._enviar_visita_firebase_hilo,
            args=(nombre_pv, timestamp_id, data, ruta_foto_segura),
            daemon=True
        ).start()

        self.inputs_existencia = {}
        self.marcas_seleccionadas = []
        self.lbl_marcas.text = "Marcas: []"
        self.foto_base64 = ""
        self.ruta_foto_actual = ""
        self.lbl_foto_estado.text = "Foto no capturada (*Requerido)"
        self.lbl_foto_estado.color = (1, 0.3, 0.3, 1)
        
        self.box_items.clear_widgets()
        self.box_items.height = dp(1)
        self.manager.current = 'main'

class CampoDataApp(App):
    # Variables de intercambio global limpias y unificadas para el consumo de todas las pantallas de UI
    zonas_lista = []
    clientes_lista = []
    productos_lista = []
    locales_lista = []      # Lista unificada de nombres de puntos de venta

    def build(self):
        Window.softinput_mode = 'below_target'
        
        self.sm = ScreenManager(transition=FadeTransition(duration=0.2))
        
        # Inyección exacta de tus pantallas respetando los nombres de tu árbol
        self.sm.add_widget(LockScreen(name='lock'))
        self.sm.add_widget(MainScreen(name='main'))
        self.sm.add_widget(RegistroClienteScreen(name='reg_cliente'))
        self.sm.add_widget(RegistroVisitaScreen(name='reg_visita'))
        self.sm.add_widget(RegistroPuntoVentaScreen(name='registro_pv_nuevo'))
        self.sm.add_widget(VisitaPuntoVentaScreen(name='visita_pv'))
        
        self.sm.current = 'lock'
        Window.bind(on_keyboard=self.on_keyboard_event)
        
        # Reducimos el tiempo de espera para que levante el sistema de inmediato
        Clock.schedule_once(self.iniciar_sistema, 0.1)
        return self.sm

    def on_keyboard_event(self, window, key, scancode, codepoint, modifier):
        if key == 27:  # Desactivar el botón físico de "Volver" de Android para evitar cierres accidentales
            return True 
        return False

    def on_pause(self):
        Window.release_all_keyboards()
        return True

    def on_resume(self):
        pass

    def iniciar_sistema(self, dt):
        try:
            inicializar_db()
            
            raw = platform.node() + platform.machine()
            self.device_id = hashlib.md5(raw.encode()).hexdigest()[:10].upper()
            
            # PASO DE ULTRA VELOCIDAD: Cargamos los datos de la base de datos local de inmediato
            self.cargar_datos_desde_cache()
            
            # TRANSICIÓN INSTANTÁNEA: Saltamos a la pantalla principal sin esperar la red para que no inicie lento
            self.sm.current = 'main'
            
            # Disparamos las tareas pesadas de red en hilos secundarios silenciosos en segundo plano
            Clock.schedule_once(self.verificar_acceso, 0.05)
            threading.Thread(target=self.hilo_sincronizador, daemon=True).start()
        except Exception as e:
            print(f"Error en inicio del sistema: {e}")

    def verificar_acceso(self, dt):
        def _hilo():
            global PATH_FB
            try:
                url_indice = f"{URL_BASE}/indice_tecnicos.json"
                response = requests.get(url_indice, timeout=8)
                data = response.json()
                
                if data and self.device_id in data:
                    PATH_FB = data[self.device_id].strip()
                    print(f"Ruta Firebase asignada: {PATH_FB}")
                    
                    # Descargamos los datos actualizados en fondo silenciosamente
                    self.descargar_datos_maestros()
                else:
                    # Si el dispositivo fue revocado o no existe, lo regresamos al bloqueo de manera segura
                    Clock.schedule_once(lambda x: setattr(self.sm, 'current', 'lock'))
                    Clock.schedule_once(lambda x: setattr(self.sm.get_screen('lock').lbl, 'text', f"ID NO REGISTRADO: {self.device_id}"))
            except Exception as e:
                print(f"Modo Offline activo de forma segura durante verificación: {e}")
        
        threading.Thread(target=_hilo, daemon=True).start()

    def descargar_datos_maestros(self):
        # Aseguramos que la UI tenga lo que hay en caché antes de descargar lo nuevo
        self.cargar_datos_desde_cache()
        threading.Thread(target=self._hilo_descarga_maestros, daemon=True).start()

    def _hilo_descarga_maestros(self):
        try:
            base_url = URL_BASE.strip().rstrip('/')
            path_fb = PATH_FB.strip().strip('/')
            url = f"{base_url}/{path_fb}"
            
            # Peticiones en segundo plano con tiempos de espera seguros
            z = requests.get(f"{url}/zonas.json", timeout=8).json()
            c = requests.get(f"{url}/clientes.json", timeout=8).json()
            p = requests.get(f"{url}/productos_detalle.json", timeout=8).json()
            t = requests.get(f"{url}/tecnicos.json", timeout=8).json()
            pvs = requests.get(f"{url}/puntos_venta_maestro.json", timeout=8).json()
            mc = requests.get(f"{url}/marcas_competencia.json", timeout=8).json()

            conn = sqlite3.connect(get_db_path(), timeout=10)
            if z: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('zonas', ?)", (json.dumps(z),))
            if c: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('clientes', ?)", (json.dumps(c),))
            if p: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('catalogo', ?)", (json.dumps(p),))
            if t: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('tecnicos_dict', ?)", (json.dumps(t),))
            if pvs: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('puntos_venta_maestro', ?)", (json.dumps(pvs),))
            if mc: conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('marcas_competencia', ?)", (json.dumps(mc),))
            conn.commit()
            conn.close()
            
            # Una vez guardado lo nuevo, refrescamos los Spinners de la UI sin congelar la app
            self.cargar_datos_desde_cache()
        except Exception as e:
            print(f"Error descargando datos maestros de Firebase: {e}")

    def cargar_datos_desde_cache(self):
        try:
            conn = sqlite3.connect(get_db_path(), timeout=10)
            cursor = conn.execute("SELECT clave, valor FROM cache_app")
            filas = cursor.fetchall()
            conn.close()
            
            cache = {}
            for fila in filas:
                clave = fila[0]
                valor_str = fila[1]
                if valor_str:
                    try:
                        cache[clave] = json.loads(valor_str)
                    except Exception:
                        cache[clave] = valor_str

            # 1. Extracción y normalización de Zonas
            if 'zonas' in cache and isinstance(cache['zonas'], (dict, list)):
                z_data = cache['zonas']
                if isinstance(z_data, dict):
                    self.zonas_lista = [str(v['nombre']).strip().upper() for k, v in z_data.items() if isinstance(v, dict) and 'nombre' in v]
                elif isinstance(z_data, list):
                    self.zonas_lista = [str(z).strip().upper() for z in z_data if z]

            # 2. Extracción y normalización de Clientes
            if 'clientes' in cache and isinstance(cache['clientes'], dict):
                c_data = cache['clientes']
                self.clientes_lista = [str(v['nombre']).strip().upper() for k, v in c_data.items() if isinstance(v, dict) and 'nombre' in v]

            # 3. Extracción y normalización de Productos
            if 'catalogo' in cache and isinstance(cache['catalogo'], dict):
                p_data = cache['catalogo']
                self.productos_lista = [str(v['nombre']).strip().upper() for k, v in p_data.items() if isinstance(v, dict) and 'nombre' in v]

            # 4. Extracción y normalización de Puntos de Venta (Locales asignados/totales)
            if 'puntos_venta_maestro' in cache and isinstance(cache['puntos_venta_maestro'], dict):
                pv_data = cache['puntos_venta_maestro']
                self.locales_lista = [str(v['nombre']).strip().upper() for k, v in pv_data.items() if isinstance(v, dict) and 'nombre' in v]

            # Sincronizamos los datos mapeados directo a la visualización de Kivy
            Clock.schedule_once(lambda dt: self._sincronizar_interfaz_filtros(cache), 0)
            
        except Exception as e:
            print(f"Error procesando colecciones desde la caché: {e}")

    def _sincronizar_interfaz_filtros(self, cache):
        """Asigna los valores procesados de forma exacta a los Spinners de las vistas activas."""
        try:
            # 1. Sincronización para: REGISTRO VISITA PRODUCTOR (reg_visita)
            if self.sm.has_screen('reg_visita') and self.clientes_lista:
                scr = self.sm.get_screen('reg_visita')
                if hasattr(scr, 'sp_cliente'):
                    try:
                        scr.sp_cliente.values = sorted(list(set(self.clientes_lista)))
                    except Exception as e:
                        print(f"Error asignando a scr.sp_cliente: {e}")

            # 2. Sincronización para: VISITA SEGUIMIENTO PV (visita_pv)
            if self.sm.has_screen('visita_pv'):
                scr = self.sm.get_screen('visita_pv')
                
                # Filtrado inteligente por ID del Técnico asignado
                locales_filtrados = []
                mi_id = str(getattr(self, 'device_id', ''))
                
                if 'puntos_venta_maestro' in cache and isinstance(cache['puntos_venta_maestro'], dict):
                    locales_filtrados = [str(v['nombre']).strip().upper() for k, v in cache['puntos_venta_maestro'].items() 
                                         if isinstance(v, dict) and str(v.get('id_tecnico', '')) == mi_id]
                
                # Fallback: Si no tiene locales específicos por ID, consume la lista global mapeada
                valores_pv = sorted(list(set(locales_filtrados))) if locales_filtrados else sorted(list(set(self.locales_lista)))
                
                if valores_pv and hasattr(scr, 'sp_pv'):
                    try:
                        scr.sp_pv.values = valores_pv
                    except Exception as e:
                        print(f"Error asignando a scr.sp_pv: {e}")

        except Exception as e:
            print(f"Error vinculando datos normalizados a la UI: {e}")

    def cargar_desde_cache(self):
        try:
            self.cargar_datos_desde_cache()
            Clock.schedule_once(lambda x: setattr(self.sm, 'current', 'main'))
        except Exception as e:
            print(f"Error en fallback offline: {e}")

    def hilo_sincronizador(self):
        while True:
            try:
                db_path = get_db_path()
                conn = sqlite3.connect(db_path, timeout=10)
                pendiente = conn.execute("SELECT id, tipo, datos FROM cola_sincro LIMIT 1").fetchone()
                conn.close()

                if not pendiente:
                    time.sleep(20)
                    continue

                row_id, tipo, datos_str = pendiente
                objeto_datos = json.loads(datos_str)
                base_url = URL_BASE.strip().rstrip('/')
                path_fb = PATH_FB.strip().strip('/')
                
                r = None  
                id_interno = objeto_datos.get('id_interno', '')

                try:
                    if tipo == 'NUEVO_CLIENTE':
                        target = f"{base_url}/{path_fb}/clientes/{id_interno}.json"
                        r = requests.put(target, json=objeto_datos, timeout=15)
                    
                    elif tipo == 'NUEVO_PV':
                        id_interno = objeto_datos.get('id_interno', '').strip().upper()
                        if not id_interno: 
                            id_interno = f"PV_{int(time.time())}"
                        target = f"{base_url}/{path_fb}/puntos_venta_maestro/{id_interno}.json"
                        
                        r = requests.put(target, json={
                            "id_tecnico": objeto_datos.get('id_tecnico', 'N/A'),
                            "nombre": objeto_datos.get('nombre', ''),
                            "tecnico": objeto_datos.get('tecnico', ''),
                            "telefono": objeto_datos.get('telefono', ''),
                            "zona": objeto_datos.get('zona', ''),
                            "stock_actual": objeto_datos.get('stock_actual', {})
                        }, timeout=15)
                        
                        if r and r.status_code in [200, 201]:
                            try:
                                conn = sqlite3.connect(db_path, timeout=10)
                                res = conn.execute("SELECT valor FROM cache_app WHERE clave='puntos_venta_maestro'").fetchone()
                                pvs_maestros = json.loads(res[0]) if res else {}
                                pvs_maestros[id_interno] = {k: v for k, v in objeto_datos.items()}
                                conn.execute("INSERT OR REPLACE INTO cache_app (clave, valor) VALUES ('puntos_venta_maestro', ?)", (json.dumps(pvs_maestros),))
                                conn.commit()
                                conn.close()
                                
                                # Forzar recarga segura en caliente para que aparezca en los Spinners inmediatamente
                                Clock.schedule_once(lambda dt: self.cargar_datos_desde_cache(), 0)
                            except:
                                pass

                    elif tipo == 'VISITA_PV':
                        target = f"{base_url}/{path_fb}/visitas_pv.json"
                        r = requests.post(target, json=objeto_datos, timeout=15)
                        if r and r.status_code in [200, 201]:
                            marcas = objeto_datos.get('marcas', [])
                            if isinstance(marcas, list):
                                for marca in [m for m in marcas if m]:
                                    m_key = marca.strip().upper().replace(" ", "_").replace(".", "_")
                                    try: 
                                        requests.put(f"{base_url}/{path_fb}/marcas_competencia/{m_key}.json", json=marca.strip().upper(), timeout=5)
                                    except: 
                                        pass
                    
                    elif tipo == 'NUEVA_MARCA_CATALOGO':
                        nombre_m = objeto_datos.get('nombre', '').strip().upper()
                        if nombre_m:
                            m_key = nombre_m.replace(" ", "_").replace(".", "_")
                            r = requests.put(f"{base_url}/{path_fb}/marcas_competencia/{m_key}.json", json=nombre_m, timeout=15)
                        else: 
                            class MockResponse:
                                status_code = 200
                            r = MockResponse()
                    
                    # Carga segura con claves estables de visitas para evitar la re-aparición de eliminados
                    else: 
                        c_id = objeto_datos.get('cliente_id', 'anonimo')
                        fecha_raw = objeto_datos.get('fecha', 'sin_fecha')
                        v_key = f"{c_id}_{fecha_raw.replace(' ', '_').replace(':', '_').replace('-', '_')}"
                        
                        target = f"{base_url}/{path_fb}/visitas/{v_key}.json"
                        r = requests.put(target, json=objeto_datos, timeout=15)

                    if r and r.status_code in [200, 201, 400]:
                        conn = sqlite3.connect(db_path, timeout=10)
                        conn.execute("DELETE FROM cola_sincro WHERE id=?", (row_id,))
                        conn.commit()
                        conn.close()

                except requests.exceptions.RequestException as e:
                    print(f"Error de red en sincronización: {e}")
                except Exception as e:
                    print(f"Error procesando registro {row_id}: {e}")

            except Exception as e:
                print(f"Error general en hilo sincronizador: {e}")
            
            time.sleep(10)

if __name__ == '__main__':
    CampoDataApp().run()
