from kivymd.app import MDApp
from kivy.lang import Builder
from kivymd.uix.list import TwoLineListItem, MDList
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
import os
import shutil
import sqlite3
import math
import json
from datetime import datetime
from kivy.app import App

# --- NUEVA FUNCIÓN PARA GESTIONAR LA RUTA DE LA DB ---
def get_db_path():
    db_nombre = 'inventario.db'
    # Esta ruta es donde Android sí permite escribir (user_data_dir)
    ruta_destino = os.path.join(App.get_running_app().user_data_dir, db_nombre)
    
    # Si la base de datos no existe en la zona de trabajo, la copiamos del APK
    if not os.path.exists(ruta_destino):
        ruta_origen = os.path.join(os.path.dirname(__file__), db_nombre)
        if os.path.exists(ruta_origen):
            shutil.copy(ruta_origen, ruta_destino)
            
    return ruta_destino

# ==========================================
# 1. CREACIÓN DE TABLAS LOCALES (OFFLINE)
# ==========================================
def preparar_base_datos_local():
    # Usamos get_db_path() para conectar
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT NOT NULL, 
            costo_bulto REAL, 
            unidades_bulto REAL, 
            ganancia_personal REAL,
            categoria TEXT DEFAULT 'Alimentos'
        );
    """)
    # Tabla definitiva para guardar las ventas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial_ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datos_json TEXT NOT NULL,
            fecha_registro TEXT
        );
    """)
    conn.commit()
    conn.close()

# ==========================================
# 2. DISEÑO DE LA INTERFAZ (KV)
# ==========================================
KV = '''
MDScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: "10dp"
        spacing: "10dp"
        
        BoxLayout:
            orientation: 'horizontal'
            spacing: "5dp"
            size_hint_y: None
            height: "50dp"
            
            MDTextField:
                id: tasa_input
                hint_text: "Tasa"
                text: "35.0"
                input_filter: "float"
                size_hint_x: 0.25
                
            MDRaisedButton:
                text: "VENTAS"
                size_hint_x: 0.35
                md_bg_color: "blue"
                font_size: "12sp"
                on_release: app.mostrar_ventas()
                
            MDRaisedButton:
                text: "CIERRE"
                size_hint_x: 0.40
                md_bg_color: "purple"
                font_size: "12sp"
                on_release: app.mostrar_cierre()
        
        MDTextField:
            id: search_input
            hint_text: "Buscar producto..."
            on_text: app.buscar_productos(self.text)
            
        MDLabel:
            text: "RESULTADOS DE BÚSQUEDA:"
            font_style: "Caption"
            size_hint_y: None
            height: "20dp"
            
        ScrollView:
            size_hint_y: 0.35
            MDList:
                id: search_list
        
        MDLabel:
            text: "CARRITO (Toca un producto para quitarlo):"
            font_style: "Caption"
            size_hint_y: None
            height: "20dp"
            
        ScrollView:
            size_hint_y: 0.35
            MDList:
                id: cart_list
                
        MDLabel:
            id: total_label
            text: "Total: 0.00 Bs"
            halign: "center"
            font_style: "H5"
            size_hint_y: None
            height: "40dp"
            
        BoxLayout:
            orientation: 'horizontal'
            spacing: "10dp"
            size_hint_y: None
            height: "50dp"
            
            MDRaisedButton:
                text: "VACIAR"
                size_hint_x: 0.3
                md_bg_color: "red"
                on_release: app.vaciar_carrito()
                
            MDRaisedButton:
                text: "COBRAR VENTA"
                size_hint_x: 0.7
                md_bg_color: "green"
                on_release: app.procesar_cobro()
'''

# ==========================================
# 3. LÓGICA PRINCIPAL DE LA APP
# ==========================================
class AppBodega(MDApp):
    carrito = []
    dialog_cantidad = None
    dialog_cobro = None
    dialog_ventas = None
    dialog_cierre = None
    dialog_confirmar = None
    dialog_detalle = None
    producto_actual = ""
    precio_actual = 0

    def build(self):
        # LLAMA A LA FUNCIÓN AQUÍ PARA QUE SE INICIALICE AL ABRIR LA APP
        preparar_base_datos_local() 
        return Builder.load_string(KV)

    # --- CÁLCULO Y BÚSQUEDA ---
    def calcular_precio(self, costo, unidades, ganancia, tasa):
        try:
            costo_unit = (float(costo) / float(unidades)) * 1.12
            precio_final = costo_unit * (1 + (float(ganancia) / 100)) * float(tasa)
            return math.floor((precio_final / 10) + 0.5) * 10
        except: 
            return 0

    def buscar_productos(self, texto):
        self.root.ids.search_list.clear_widgets()
        if not texto:
            return
            
        tasa = self.root.ids.tasa_input.text or "35.0"
        
        try:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, costo_bulto, unidades_bulto, ganancia_personal FROM productos WHERE nombre LIKE ?", ('%' + texto + '%',))
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                nombre, costo, unidades, ganancia = row
                precio = self.calcular_precio(costo, unidades, ganancia, tasa)
                
                item = TwoLineListItem(
                    text=f"{nombre}", 
                    secondary_text=f"Precio Unitario: {precio} Bs"
                )
                item.bind(on_release=lambda x, n=nombre, p=precio: self.abrir_dialogo_cantidad(n, p))
                self.root.ids.search_list.add_widget(item)
        except Exception as e:
            print(f"Error en base de datos: {e}")

    # --- GESTIÓN DEL CARRITO ---
    def abrir_dialogo_cantidad(self, nombre, precio):
        self.producto_actual = nombre
        self.precio_actual = precio
        
        self.input_cantidad = MDTextField(
            hint_text="¿Cuántas unidades?",
            text="1",
            input_filter="int"
        )
        
        self.dialog_cantidad = MDDialog(
            title=f"Agregar: {nombre}",
            type="custom",
            content_cls=self.input_cantidad,
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda x: self.dialog_cantidad.dismiss()),
                MDFlatButton(text="AGREGAR", on_release=self.confirmar_agregar),
            ],
        )
        self.dialog_cantidad.open()

    def confirmar_agregar(self, *args):
        try:
            cantidad = int(self.input_cantidad.text)
            if cantidad <= 0: cantidad = 1
        except:
            cantidad = 1
            
        subtotal = self.precio_actual * cantidad
        
        self.carrito.append({
            'nombre': self.producto_actual,
            'precio': self.precio_actual,
            'cantidad': cantidad,
            'subtotal': subtotal
        })
        
        self.dialog_cantidad.dismiss()
        self.actualizar_vista_carrito()
        self.root.ids.search_input.text = ""

    def actualizar_vista_carrito(self):
        self.root.ids.cart_list.clear_widgets()
        total = 0
        
        for i, item in enumerate(self.carrito):
            nombre = item['nombre']
            cant = item['cantidad']
            subtotal = item['subtotal']
            total += subtotal
            
            fila = TwoLineListItem(
                text=f"{nombre} (x{cant})", 
                secondary_text=f"Subtotal: {subtotal} Bs (Toca quitar)"
            )
            fila.bind(on_release=lambda x, idx=i: self.quitar_producto(idx))
            self.root.ids.cart_list.add_widget(fila)
            
        self.root.ids.total_label.text = f"Total a Pagar: {total} Bs"

    def quitar_producto(self, index):
        if 0 <= index < len(self.carrito):
            self.carrito.pop(index)
            self.actualizar_vista_carrito()

    def vaciar_carrito(self):
        self.carrito = []
        self.actualizar_vista_carrito()
        self.root.ids.search_input.text = ""

    # --- PROCESO DE COBRO ---
    def procesar_cobro(self):
        if not self.carrito:
            self.mostrar_alerta("Carrito vacío", "No hay productos para cobrar.")
            return

        total_venta = sum(item['subtotal'] for item in self.carrito)

        self.input_cliente = MDTextField(hint_text="Cliente (Opcional)", text="General")
        self.input_efectivo = MDTextField(hint_text="Efectivo Bs", text=str(total_venta), input_filter="float")
        self.input_punto = MDTextField(hint_text="Punto de Venta Bs", text="0", input_filter="float")
        self.input_movil = MDTextField(hint_text="Pago Móvil Bs", text="0", input_filter="float")
        self.input_ref_movil = MDTextField(hint_text="Ref. Pago Móvil (Últimos dígitos)", text="")
        self.input_fiado = MDTextField(hint_text="Fiado / Crédito Bs", text="0", input_filter="float")

        layout_interno = BoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        layout_interno.bind(minimum_height=layout_interno.setter('height'))
        
        layout_interno.add_widget(self.input_cliente)
        layout_interno.add_widget(self.input_efectivo)
        layout_interno.add_widget(self.input_punto)
        layout_interno.add_widget(self.input_movil)
        layout_interno.add_widget(self.input_ref_movil)
        layout_interno.add_widget(self.input_fiado)

        scroll_pagos = ScrollView(size_hint=(1, None), height="350dp")
        scroll_pagos.add_widget(layout_interno)

        self.dialog_cobro = MDDialog(
            title=f"Cobrar: {total_venta} Bs",
            type="custom",
            content_cls=scroll_pagos,
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda x: self.dialog_cobro.dismiss()),
                MDFlatButton(text="REGISTRAR", on_release=self.validar_y_guardar_venta)
            ],
        )
        self.dialog_cobro.open()

    def validar_y_guardar_venta(self, *args):
        try:
            total_venta = sum(item['subtotal'] for item in self.carrito)
            efectivo = float(self.input_efectivo.text or 0)
            punto = float(self.input_punto.text or 0)
            movil = float(self.input_movil.text or 0)
            ref_movil = self.input_ref_movil.text.strip()
            fiado = float(self.input_fiado.text or 0)
            cliente = self.input_cliente.text.strip() or "General"
            tasa_usada = float(self.root.ids.tasa_input.text or "35.0")
            
            total_ingresado = efectivo + punto + movil + fiado
            if total_ingresado < total_venta:
                self.mostrar_alerta("Error", "El monto pagado es menor al total de la venta.")
                return

            if movil > 0 and ref_movil == "":
                self.mostrar_alerta("Falta Referencia", "Has ingresado un monto en Pago Móvil, debes escribir la referencia.")
                return

            datos_venta = {
                "detalle": {
                    "total_bs": total_venta,
                    "efectivo": efectivo,
                    "punto": punto,
                    "movil": movil,
                    "ref_movil": ref_movil,
                    "fiado": fiado,
                    "cliente": cliente,
                    "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "tasa_momento": tasa_usada
                },
                "items": [
                    {"producto_nombre": i['nombre'], "cantidad": i['cantidad'], "precio_unitario": i['precio']} 
                    for i in self.carrito
                ]
            }

            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("INSERT INTO historial_ventas (datos_json, fecha_registro) VALUES (?, ?)",
                           (json.dumps(datos_venta), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

            self.dialog_cobro.dismiss()
            self.mostrar_alerta("✅ Venta Registrada", "La venta se guardó localmente con éxito.")
            self.vaciar_carrito()

        except Exception as e:
            self.mostrar_alerta("Error", f"Ocurrió un error: {str(e)}")

    # --- VER HISTORIAL Y DETALLES DE VENTAS ---
    def mostrar_ventas(self):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT id, datos_json, fecha_registro FROM historial_ventas ORDER BY id DESC")
        ventas = cursor.fetchall()
        conn.close()

        if not ventas:
            self.mostrar_alerta("Historial Vacío", "No hay ventas registradas en el sistema.")
            return

        lista = MDList()
        for v in ventas:
            id_venta = v[0]
            datos = json.loads(v[1])
            fecha = v[2]
            detalles = datos.get('detalle', {})
            total = detalles.get('total_bs', 0)
            cliente = detalles.get('cliente', 'General')

            item = TwoLineListItem(
                text=f"Venta #{id_venta} - {fecha}",
                secondary_text=f"Cliente: {cliente} | Total: {total} Bs"
            )
            # Al tocar un ítem, abre el detalle
            item.bind(on_release=lambda x, d=datos, i=id_venta: self.ver_detalle_venta(d, i))
            lista.add_widget(item)

        scroll = ScrollView(size_hint=(1, None), height="350dp")
        scroll.add_widget(lista)

        self.dialog_ventas = MDDialog(
            title="Historial de Ventas (Toca para ver detalle)",
            type="custom",
            content_cls=scroll,
            buttons=[
                MDFlatButton(text="EXPORTAR EXCEL", md_bg_color="green", on_release=self.exportar_excel),
                MDFlatButton(text="CERRAR", on_release=lambda x: self.dialog_ventas.dismiss())
            ]
        )
        self.dialog_ventas.open()

    def ver_detalle_venta(self, datos, id_venta):
        detalles = datos.get('detalle', {})
        items = datos.get('items', [])
        
        prod_text = ""
        for i in items:
            prod_text += f"• {i['producto_nombre']} (x{i['cantidad']}): {i['precio_unitario'] * i['cantidad']} Bs\n"
        
        efectivo = float(detalles.get('efectivo', 0))
        punto = float(detalles.get('punto', 0))
        movil = float(detalles.get('movil', 0))
        fiado = float(detalles.get('fiado', 0))
        total_bs = float(detalles.get('total_bs', 0))
        cobrado = efectivo + punto + movil
        estado = "SOLVENTE" if fiado <= 0 else "PENDIENTE (FIADO)"
        
        info_text = (
            f"Fecha: {detalles.get('fecha_hora', '')}\n"
            f"Cliente: {detalles.get('cliente', 'General')}\n\n"
            f"PRODUCTOS VENDIDOS:\n"
            f"{prod_text}\n"
            f"--- INFORMACIÓN DE PAGO ---\n"
            f"✅ COBRADO (entró a caja): {cobrado} Bs\n\n"
            f"💵 Efectivo: {efectivo} Bs       💳 Punto: {punto} Bs\n"
            f"📱 Pago Móvil: {movil} Bs\n"
            f"Estado: {estado}\n\n"
            f"📝 Fiado/Crédito: {fiado} Bs\n"
        )
        
        scroll = ScrollView(size_hint=(1, None), height="320dp")
        lbl = MDLabel(text=info_text, theme_text_color="Secondary", size_hint_y=None)
        lbl.bind(texture_size=lbl.setter('size'))
        scroll.add_widget(lbl)
        
        self.dialog_detalle = MDDialog(
            title=f"Detalle Venta #{id_venta}",
            type="custom",
            content_cls=scroll,
            buttons=[
                MDFlatButton(text="CERRAR", on_release=lambda x: self.dialog_detalle.dismiss())
            ]
        )
        self.dialog_detalle.open()

    # --- EXPORTAR EXCEL ---
    def exportar_excel(self, *args):
        import csv
        
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT id, datos_json, fecha_registro FROM historial_ventas ORDER BY id ASC")
        ventas = cursor.fetchall()
        
        if not ventas:
            conn.close()
            self.mostrar_alerta("Error", "No hay ventas para exportar.")
            return
            
        # Mejora de Android: Se guarda en el directorio de usuario seguro de la App
        nombre_archivo = os.path.join(
            App.get_running_app().user_data_dir, 
            f"Ventas_Exportadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        # Obtener categorías de la base de datos local para la exportación
        cursor.execute("SELECT nombre, categoria FROM productos")
        cat_dict = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        
        try:
            # Escribe el archivo CSV
            with open(nombre_archivo, mode='w', newline='', encoding='utf-8') as archivo_csv:
                writer = csv.writer(archivo_csv, delimiter=',')
                
                # Encabezados idénticos a tu archivo Excel
                headers = [
                    'Factura #', 'Fecha', 'Cliente', 'Producto', 'Categoría', 'Codigo', 
                    'Cant', 'Precio Unit Bs', 'Subtotal Producto', 'Total Factura Bs', 
                    'Pago Efectivo', 'Pago Punto', 'Pago Movil', 'Total Cobrado Bs', 
                    'Fiado Bs', 'Estado', 'Ref Movil', 'Fiao/Crédito USD', 
                    'Deuda Origen', 'Categoría_norm', 'es_chucherias', 'es_deuda_sys'
                ]
                writer.writerow(headers)
                
                for v in ventas:
                    id_venta = v[0]
                    datos = json.loads(v[1])
                    detalles = datos.get('detalle', {})
                    items = datos.get('items', [])
                    
                    fecha = detalles.get('fecha_hora', '')
                    cliente = detalles.get('cliente', 'General')
                    efectivo = float(detalles.get('efectivo', 0))
                    punto = float(detalles.get('punto', 0))
                    movil = float(detalles.get('movil', 0))
                    total_cobrado = efectivo + punto + movil
                    total_factura = float(detalles.get('total_bs', 0))
                    fiado = float(detalles.get('fiado', 0))
                    estado = "SOLVENTE" if fiado <= 0 else "PENDIENTE"
                    ref_movil = detalles.get('ref_movil', '')
                    
                    for i in items:
                        producto = i['producto_nombre']
                        cant = i['cantidad']
                        precio_u = float(i['precio_unitario'])
                        subtotal = cant * precio_u
                        categoria = cat_dict.get(producto, "General")
                        
                        cat_norm = str(categoria).lower()
                        es_chuche = "True" if "chucheria" in cat_norm else "False"
                        
                        # Genera cada fila desglosando el producto exacto
                        row = [
                            id_venta, fecha, cliente, producto, categoria, "N/A",
                            cant, precio_u, subtotal, total_factura,
                            efectivo, punto, movil, total_cobrado,
                            fiado, estado, ref_movil, 0.0, 
                            "N/A", cat_norm, es_chuche, "False"
                        ]
                        writer.writerow(row)
            
            if self.dialog_ventas:
                self.dialog_ventas.dismiss()
                
            self.mostrar_alerta("✅ Éxito", f"Archivo generado correctamente.\nRuta: {nombre_archivo}")
        except Exception as e:
            self.mostrar_alerta("Error", f"No se pudo exportar el archivo: {str(e)}")

    # --- CIERRE DE CAJA ---
    def mostrar_cierre(self):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT datos_json FROM historial_ventas")
        ventas = cursor.fetchall()
        conn.close()

        total_efectivo = 0
        total_punto = 0
        total_movil = 0
        total_fiado = 0
        gran_total = 0

        for v in ventas:
            datos = json.loads(v[0])
            det = datos.get('detalle', {})
            total_efectivo += float(det.get('efectivo', 0))
            total_punto += float(det.get('punto', 0))
            total_movil += float(det.get('movil', 0))
            total_fiado += float(det.get('fiado', 0))
            gran_total += float(det.get('total_bs', 0))

        ingresos_reales = total_efectivo + total_punto + total_movil

        texto_cierre = (
            f"Transacciones Totales: {len(ventas)}\n\n"
            f"💵 Efectivo: {total_efectivo:.2f} Bs\n"
            f"💳 Punto de Venta: {total_punto:.2f} Bs\n"
            f"📱 Pago Móvil: {total_movil:.2f} Bs\n"
            f"📝 Fiado/Crédito: {total_fiado:.2f} Bs\n"
            f"-----------------------------------\n"
            f"💰 TOTAL EN CAJA: {ingresos_reales:.2f} Bs\n"
            f"📊 VENTA BRUTA (Con fiado): {gran_total:.2f} Bs"
        )

        contenedor = BoxLayout(orientation="vertical", size_hint_y=None, height="200dp")
        lbl = MDLabel(text=texto_cierre, theme_text_color="Secondary")
        contenedor.add_widget(lbl)

        self.dialog_cierre = MDDialog(
            title="Cierre de Caja del Día",
            type="custom",
            content_cls=contenedor,
            buttons=[
                MDFlatButton(text="VACIAR CAJA", text_color=(1, 0, 0, 1), on_release=self.confirmar_limpiar_caja),
                MDFlatButton(text="CERRAR", on_release=lambda x: self.dialog_cierre.dismiss())
            ]
        )
        self.dialog_cierre.open()

    def confirmar_limpiar_caja(self, *args):
        self.dialog_confirmar = MDDialog(
            title="¿Vaciar Caja?",
            text="Esto borrará TODAS las ventas registradas y pondrá el cierre en cero. ¿Estás seguro de que quieres iniciar un nuevo día?",
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda x: self.dialog_confirmar.dismiss()),
                MDFlatButton(text="SÍ, BORRAR", text_color=(1, 0, 0, 1), on_release=self.vaciar_caja_confirmado)
            ]
        )
        self.dialog_confirmar.open()

    def vaciar_caja_confirmado(self, *args):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historial_ventas")
        conn.commit()
        conn.close()
        
        if self.dialog_confirmar: self.dialog_confirmar.dismiss()
        if self.dialog_cierre: self.dialog_cierre.dismiss()
        
        self.mostrar_alerta("Caja Limpia", "El historial de ventas se ha borrado correctamente. Listo para registrar un nuevo día.")

    def mostrar_alerta(self, titulo, mensaje):
        dialogo_info = MDDialog(
            title=titulo,
            text=mensaje,
            buttons=[MDFlatButton(text="OK", on_release=lambda x: dialogo_info.dismiss())]
        )
        dialogo_info.open()

if __name__ == '__main__':
    AppBodega().run()