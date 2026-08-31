import os,sys,time,datetime
import getpass
import polars as pl
import win32com.client

def Revisar_carpetas(Enviar_mensaje = True):
    # Obtener el nombre de usuario actual del sistema
    username = getpass.getuser().lower() + "\\Documents\\Macro"

    # Construir la ruta de forma segura usando os.path.join
    user_macro = os.path.join("C:\\Users", username)
    user_python = os.path.join(user_macro, "RPA_descargas_py")

    # Verificar si la ruta existe
    if not os.path.exists(user_macro):
        print(f"Se creo la carpeta : {user_macro}")

    if not os.path.exists(user_python):
        os.makedirs(user_python,exist_ok=True)
        print(f"Se creo la carpeta : {user_python}")
    if Enviar_mensaje : 
        print("✅ Termino la revision de carpetas 📁 ✅")
    return user_python

# Diseñado solo para el archivo ZLO_PEDIVAL_2.TXT  -> SAP TRX SQ01 - ZLO_PEDI_VAL_2
def Leer_archivo_txt(ruta_txt,solo_material=False) -> pl.DataFrame :

    df = pl.read_csv(ruta_txt,separator='\t',encoding='latin-1',skip_rows=6,infer_schema_length=0,columns=range(2,45),skip_rows_after_header=1,quote_char=None)
    df = df.drop(df.columns[1:4],df.columns[6],df.columns[8:12],df.columns[13],df.columns[17:19],df.columns[21:25],df.columns[26:42])
    df = df.rename({ df.columns[0]:'OT' ,  df.columns[1]:'clase_documento' ,  df.columns[2]:'fecha_creado' ,  df.columns[3]:'creado_por' ,  df.columns[4]:'CD',
                    df.columns[5]:'Material',  df.columns[6]:'Descripcion',  df.columns[7]:'Destino',  df.columns[8]:'Cantidad_UMP' ,  df.columns[9]:'UMP',
                    df.columns[10]:'fecha_entrega',  df.columns[11]:'Cantidad_entregada' })
    df = df.filter( pl.col('OT').is_not_null() )
    df = df.with_columns( pl.col('OT').cast(pl.Int64),
                    pl.col('Cantidad_UMP','Cantidad_entregada').str.strip_chars().str.replace(',','').str.to_decimal(scale=3).cast(pl.Float64),
                    pl.col('fecha_creado','fecha_entrega').str.to_date('%d.%m.%Y'),
                    pl.lit( datetime.datetime.now() ).cast(pl.Datetime).alias('fecha_hora_actualizacion') )
    if solo_material:
        df = df['Material'].unique().clone()
    return df

def Leer_marm_txt(ruta_txt):
    df = pl.read_csv(ruta_txt,separator='\t',encoding='latin-1',skip_rows=6,infer_schema_length=0,columns=range(2,12),skip_rows_after_header=1)
    df = df.drop(df.columns[1])
    df = df.rename({ df.columns[0]:'Material', df.columns[1]:'Contador', df.columns[2]:'UMA', df.columns[3]:'Longitud', df.columns[4]:'Ancho', df.columns[5]:'Altura',
                    df.columns[6]:'Volumen', df.columns[7]:'UV', df.columns[8]:'Peso' })
    df = df.filter( pl.col('Material').is_not_null() )
    df = df.with_columns( pl.col('Contador','Longitud','Ancho','Altura','Peso').str.strip_chars().str.replace(',','').str.to_decimal(scale=3).cast(pl.Float64),
                         pl.lit( datetime.datetime.now() ).cast(pl.Datetime).alias('fecha_hora_actualizacion') )
    return df


def Leer_MM60_txt(ruta_txt):
    df = pl.read_csv(ruta_txt,separator='\t',encoding='latin-1',skip_rows=3,infer_schema_length=0,columns=range(1,8),skip_rows_after_header=1,quote_char=None)
    df = df.rename({ df.columns[0]:'CD', df.columns[1]:'Material', df.columns[2]:'Descripcion', df.columns[3]:'Precio', df.columns[4]:'UMB', df.columns[5]:'Grupo_compra',
                df.columns[6]:'cod_articulo' })
    df = df.with_columns( pl.col('Precio').str.strip_chars().str.replace(',','').str.to_decimal(scale=4).cast(pl.Float64), 
                         pl.lit( datetime.datetime.now() ).cast(pl.Datetime).alias('fecha_hora_actualizacion') )
    return df

def conexion_a_sap():
    try:
        sap_gui_auto = win32com.client.GetObject("SAPGUI")
    except Exception as e:
        print("SAP esta cerrado , Abrelo -_- ")
        sys.exit()

    if not sap_gui_auto:
        print('🚨 Esta cerrado SAP , inicialo y logeate 🚨')
        sys.exit()
    application = sap_gui_auto.GetScriptingEngine
    if application.Connections.Count == 0:
        print('🚨 No estas Logeado a SAP 🚨')
        sys.exit()
    connection = application.Children(0)

    session = connection.Children(0)
    total_conexiones = connection.children.count
    while total_conexiones < 5:
        session.createsession()
        time.sleep(2.5)
        total_conexiones+=1
    print("✅ Conexion a Sap Exitosa ✅")
    return session