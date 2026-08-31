import SAP_,os,gc,time
from Auxiliar import Leer_archivo_txt
from Auxiliar import Leer_marm_txt
from Auxiliar import Leer_MM60_txt
from Auxiliar import Revisar_carpetas
from duckdb_queries import ejecutar_querys
import duckdb

# control de tiempo del script
inicio = time.perf_counter()

try:
    fecha_inicio , fecha_fin = SAP_.Descargar_datos_SAP()

    ruta_ = Revisar_carpetas(False)
    ruta_zlo_pedi_val = os.path.join(ruta_,"ZLO_PEDI_VAL_2.txt")
    ruta_marm = os.path.join(ruta_,"MARM.txt")
    ruta_mm60 = os.path.join(ruta_,"MM60.txt")

    # Tablas de los archivos descargados
    df_zlo_pedi_val = Leer_archivo_txt(ruta_zlo_pedi_val)
    df_marm = Leer_marm_txt(ruta_marm)
    df_mm60 = Leer_MM60_txt(ruta_mm60)

    fin = time.perf_counter()
    print(f"Se termino de leer los archivos TXT en = {(fin-inicio)/60:.2f}")

    # base de datos
    disco_ = 'R:' if os.path.exists('R:') else 'V:'
    # ruta_db = os.path.join(disco_,r"\GGG200_Planifi y Ctrl de Procesos_Información Logística\Tablas maestros\Bases de datos\DB_Proyeccion.duckdb")
    ruta_db = r'C:\Users\rtintame\Desktop\Proyectado_OT\DB\DB_Proyeccion.duckdb'

    ejecutar_querys(ruta_db, df_zlo_pedi_val , df_marm, df_mm60 , fecha_inicio, fecha_fin )


except Exception as e:
    print(f"Hubo un error {e}")
finally:
    #   LIMPIEZA
    del df_zlo_pedi_val,df_marm,df_mm60
    fin = time.perf_counter()
    minuto_ = (fin-inicio)/60
    print(f"Termino Proceso Compelto del Script en  = {minuto_:.2f} minutos ")

    #  La libreria gc  libera memoria de inmediato
    gc.collect()

