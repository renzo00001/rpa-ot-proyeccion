import os,pyperclip
import polars as pl
from datetime import timedelta
from datetime import datetime
from Auxiliar import Revisar_carpetas
from Auxiliar import Leer_archivo_txt
from Auxiliar import conexion_a_sap

def Descargar_datos_SAP():
    Ruta_descargas = Revisar_carpetas()

    # 1. Conexión al GUI de SAP
    session = conexion_a_sap()

    fecha_inicio = datetime.now() + timedelta(days = -14)
    fecha_inicio_ini_sql = fecha_inicio.strftime('%Y-%m-%d')
    fecha_inicio = fecha_inicio.strftime('%d.%m.%Y')

    fecha_fin = datetime.now() + timedelta(days = 7)
    fecha_inicio_fin_sql = fecha_fin.strftime('%Y-%m-%d')
    fecha_fin = fecha_fin.strftime('%d.%m.%Y')

    # Descargar ZLO_PEDI_VAL_2
    session.starttransaction ("SQ01")
    session.findById("wnd[0]/usr/ctxtRS38R-QNUM").Text = "ZLO_PEDI_VAL_2"
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[17]").press()
    session.findById("wnd[1]/usr/txtV-LOW").Text = "proyectado_OT"
    session.findById("wnd[1]/usr/txtENAME-LOW").Text = ""
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/usr/ctxtSP$00029-LOW").Text = fecha_inicio
    session.findById("wnd[0]/usr/ctxtSP$00029-HIGH").Text = fecha_fin
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").pressToolbarContextButton ("&MB_EXPORT")
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").selectContextMenuItem ("&PC")
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").Select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").SetFocus()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ctxtDY_PATH").Text = Ruta_descargas
    session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = "ZLO_PEDI_VAL_2.txt"
    session.findById("wnd[1]/tbar[0]/btn[11]").press()


    # Descargando la MARM de los materiales
    df = Leer_archivo_txt( os.path.join(Ruta_descargas,"ZLO_PEDI_VAL_2.txt") , True )
    materiales_ = "\r\n".join(df)

    session.starttransaction ("SQ01")
    session.findById("wnd[0]/usr/ctxtRS38R-QNUM").Text = "ZLO_MARM"
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[17]").press()
    session.findById("wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell").setCurrentCell (5, "TEXT")
    session.findById("wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell").selectedRows = "5"
    session.findById("wnd[1]/tbar[0]/btn[2]").press()
    session.findById("wnd[0]/usr/btn%_SP$00001_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[16]").press()
    pyperclip.copy(materiales_)
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").pressToolbarContextButton ("&MB_EXPORT")
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").selectContextMenuItem ("&PC")
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").Select()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ctxtDY_PATH").Text = Ruta_descargas
    session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = "MARM.txt"
    session.findById("wnd[1]/tbar[0]/btn[11]").press()


    # Descargando la MM60-Precio de los materiales
    session.starttransaction ("MM60")
    session.findById("wnd[0]/tbar[1]/btn[17]").press()
    session.findById("wnd[1]/usr/txtV-LOW").Text = "var_prc"
    session.findById("wnd[1]/usr/txtENAME-LOW").Text = ""
    session.findById("wnd[1]").sendVKey(0)
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/usr/btn%_MS_MATNR_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[16]").press()

    pyperclip.copy(materiales_)

    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[33]").press()
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").currentCellRow = -1
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").selectColumn ("VARIANT")
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").contextMenu()
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").selectContextMenuItem ("&FILTER")
    session.findById("wnd[2]/usr/ssub%_SUBSCREEN_FREESEL:SAPLSSEL:1105/ctxt%%DYN001-LOW").Text = "/PENDAVIS"
    session.findById("wnd[2]/usr/ssub%_SUBSCREEN_FREESEL:SAPLSSEL:1105/ctxt%%DYN001-LOW").caretPosition = 9
    session.findById("wnd[2]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").selectedRows = "0"
    session.findById("wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell").clickCurrentCell()
    session.findById("wnd[0]/tbar[1]/btn[45]").press()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").Select()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ctxtDY_PATH").Text = Ruta_descargas
    session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = "MM60.txt"
    session.findById("wnd[1]/tbar[0]/btn[11]").press()


    return fecha_inicio_ini_sql,fecha_inicio_fin_sql


def Descargar_SQ01_OT(df_OT:pl.DataFrame)-> pl.DataFrame:

    session = conexion_a_sap()
    Ruta_descargas = Revisar_carpetas(False)
    lista_ot = "\r\n".join(df_OT['OT'].cast(pl.String).to_list())

    session.starttransaction("SQ01")
    session.findById("wnd[0]/usr/ctxtRS38R-QNUM").text = "ZLO_RPT_FENTRE"
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[17]").press()
    session.findById("wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell").setCurrentCell (1,"TEXT")
    session.findById("wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell").selectedRows = "1"
    session.findById("wnd[1]/tbar[0]/btn[2]").press()
    session.findById("wnd[0]/usr/btn%_SP$00002_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[16]").press()
    pyperclip.copy(lista_ot)
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").pressToolbarContextButton ("&MB_EXPORT")
    session.findById("wnd[0]/usr/cntlCONTAINER/shellcont/shell").selectContextMenuItem ("&PC")
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").Select()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ctxtDY_PATH").Text = Ruta_descargas
    session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = "ZLO_RPT_FENTRE.txt"
    session.findById("wnd[1]/tbar[0]/btn[11]").press()

    ruta_ = os.path.join(Ruta_descargas , "ZLO_RPT_FENTRE.txt")

    df = pl.read_csv(ruta_,separator='\t',encoding='latin-1',skip_rows=6,infer_schema_length=0,columns=range(1,14),skip_rows_after_header=1,quote_char=None)
    df = df.rename({ df.columns[5]:'Tienda', df.columns[6]:'Material', df.columns[11]:'Restar_dias' })
    df = df.drop( df.columns[0:5], df.columns[7:11] , df.columns[12]   )
    df = df.unique()
    df = df.with_columns( pl.col('Tienda','Material').str.strip_chars(), pl.col('Restar_dias').str.strip_chars().str.to_integer().cast(pl.Int32),
                            pl.lit( datetime.now() ).cast(pl.Datetime).alias('fecha_hora_actualizacion') )
    return df

def descargar_maestro(df_material)-> pl.DataFrame:

    session = conexion_a_sap()
    Ruta_descargas = Revisar_carpetas(False)
    lista_ot = "\r\n".join(df_material['Material'].cast(pl.String).to_list())

    session.starttransaction("ZVAB0006")
    session.findById("wnd[0]/tbar[1]/btn[17]").press()
    session.findById("wnd[1]/usr/txtV-LOW").text = "/PENDIENTE"
    session.findById("wnd[1]/usr/txtENAME-LOW").text = ""
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/usr/chkP_NOSURT").selected = True
    session.findById("wnd[0]/usr/btn%_S_WERKS_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[16]").press()
    session.findById("wnd[1]/usr/tabsTAB_STRIP/tabpSIVA/ssubSCREEN_HEADER:SAPLALDB:3010/tblSAPLALDBSINGLE/ctxtRSCSEL_255-SLOW_I[1,0]").text = "CD*"
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/usr/btn%_S_MATNR_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[16]").press()
    pyperclip.copy(lista_ot)
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/tbar[1]/btn[45]").press()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").select()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
    session.findById("wnd[1]/usr/ctxtDY_PATH").Text = Ruta_descargas
    session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = "ZVAB0006.txt"
    session.findById("wnd[1]/tbar[0]/btn[11]").press()


    ruta_ = os.path.join(Ruta_descargas , "ZVAB0006.txt")
    df = pl.read_csv(ruta_,separator='\t',encoding='latin-1',skip_rows=3,infer_schema_length=0,columns=range(1,16),skip_rows_after_header=1,quote_char=None)
    df = df.drop(df.columns[3])
    df = df.rename({ df.columns[0]:'COD_material', df.columns[1]:'Marca', df.columns[2]:'RUC', df.columns[3]:'Nombre Proveedor' , df.columns[4]:'DESC_material',
                    df.columns[5]:'COD_EAN', df.columns[6]:'COD_articulo', df.columns[7]:'DESC_articulo', df.columns[8]:'COD_grupo_compras', 
                    df.columns[9]:'DESC_grupo_compras',df.columns[10]:'DESC_categoria', df.columns[11]:'DESC_subcategoria',
                    df.columns[12]:'gerencia', df.columns[13]:'unidad_de_negocio' })
    df = df.unique()
    df = df.with_columns( pl.col('RUC','COD_articulo','COD_EAN','COD_grupo_compras').str.strip_chars().str.to_integer().cast(pl.Int64),
                        pl.when( pl.col('gerencia') == 'FOOD' ).then( pl.lit('FOOD ABARROTES') ).otherwise( pl.col('gerencia') ).alias('gerencia'),
                        pl.lit( datetime.now() ).cast(pl.Datetime).alias('fecha_hora_actualizacion') )
    return df