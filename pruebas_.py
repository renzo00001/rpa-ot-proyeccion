from Auxiliar import Leer_archivo_txt
from Auxiliar import conexion_a_sap
import os

Ruta_descargas = r'C:\Users\rtintame\Documents\Macro\RPA_descargas_py\ZLO_PEDI_VAL_2.txt'
df = Leer_archivo_txt( Ruta_descargas , True )

# print( "\r\n".join(df))

conexion_a_sap()
