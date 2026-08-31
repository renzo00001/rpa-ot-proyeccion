import duckdb
import polars as pl
from SAP_ import Descargar_SQ01_OT
from SAP_ import descargar_maestro

def ejecutar_querys(ruta_db,df_zlo_pedi_val:pl.DataFrame ,df_marm:pl.DataFrame ,df_mm60:pl.DataFrame ,fecha_inicio,fecha_fin):

    try:
        conn = duckdb.connect(ruta_db)
        # ACTUALIZAR BASE DE DATOS 
        conn.execute(f""" 
                    DELETE FROM proyectado WHERE fecha_entrega BETWEEN '{fecha_inicio}' AND '{fecha_fin}';
                    INSERT INTO proyectado SELECT * FROM df_zlo_pedi_val;

                    DELETE FROM MARM;
                    INSERT INTO MARM SELECT * FROM df_marm;

                    DELETE FROM MM60;
                    INSERT INTO MM60 SELECT * FROM df_mm60;
                    
                    INSTALL EXCEL;
                    LOAD EXCEL;
        """)


        # Revisar tiendas y materiales no registrados en la tabla cfg_ajuste_fecha_entrega  ->  OT
        df = conn.sql("""  SELECT DISTINCT(pr_.OT) AS OT FROM proyectado AS pr_
                LEFT JOIN cfg_ajuste_fecha_entrega AS cfg
                ON pr_.Destino = cfg.Tienda AND pr_.Material = cfg.Material
                WHERE cfg.Restar_dias IS NULL AND NOT pr_.clase_documento = 'ZEMT'  """).pl()
        if df.shape[0] > 0 :
            # Buscar y descargar las tiendas y materiales ligadas a las OT en SAP
            df_sap = Descargar_SQ01_OT(df)
            conn.sql(""" INSERT INTO cfg_ajuste_fecha_entrega SELECT * FROM df_sap """)

        # Revisar si hay existencia de los materiales en el MAESTRO
        df = conn.sql(""" 
            SELECT DISTINCT(pr_.Material) FROM proyectado AS pr_
            LEFT JOIN maestro AS m_
            ON pr_.Material = m_.COD_material
            WHERE m_.COD_material IS NULL
        """).pl()
        if df.shape[0] > 0 :
            df_maestro = descargar_maestro(df)
            conn.sql(""" INSERT INTO maestro SELECT * FROM df_maestro """)


        # Exportar Archivo Excel
        ruta_xlsx = r'C:\Users\rtintame\Desktop\Proyectado_OT\Acumulado\example.xlsx'
        conn.sql(rf""" 
            COPY(
            WITH precio_filtrado AS (
                SELECT m_.Material,m_.Contador,m_.UMA,mm_.Precio
                FROM MARM AS m_
                LEFT JOIN MM60 AS mm_
                ON m_.Material = mm_.Material AND m_.UMA = mm_.UMB
                WHERE mm_.Precio IS NOT NULL
            ), contador_filtrado AS(
                SELECT m_.Material,m_.Contador,m_.UMA
                FROM MARM AS m_
                LEFT JOIN MM60 AS mm_
                ON m_.Material = mm_.Material AND m_.UMA = mm_.UMB
                WHERE mm_.Precio IS NULL 
            ), MARM_actualizado AS (
                SELECT c_.*, p_.Contador AS contador_UMB,p_.UMA AS UMB ,p_.Precio AS Precio_UMB
                FROM contador_filtrado AS c_
                LEFT JOIN precio_filtrado AS p_
                ON c_.Material = p_.Material
            ), Unicos_cfg_fecha_entrega AS (
                SELECT DISTINCT ON (Tienda , Material) * FROM cfg_ajuste_fecha_entrega
            ),
            tabla_final AS (
            SELECT 
                pr_.*,
                CASE WHEN pr_.Cantidad_entregada > 0 THEN 'generado'
                    ELSE 'pendiente'
                END AS Status,
                pr_.Cantidad_UMP * COALESCE(m_.Contador,1)   AS cantidad_base,
                COALESCE(m_.UMB, pr_.UMP ) AS UMB,
                (pr_.Cantidad_UMP * COALESCE(m_.Contador,1) ) * COALESCE(m_.Precio_UMB,mm_.Precio) AS Importe,
                
                CASE 
                    WHEN pr_.clase_documento = 'ZEMT' THEN pr_.fecha_creado
                    ELSE (pr_.fecha_entrega - cfg.Restar_dias * INTERVAL '1 day')::DATE
                END AS fecha_entrega_actualizada,
                
                ma_.gerencia,ma_.unidad_de_negocio

            FROM proyectado AS pr_
            LEFT JOIN MARM_actualizado AS m_
            ON pr_.Material = m_.Material AND pr_.UMP = m_.UMA
            LEFT JOIN precio_filtrado AS mm_
            ON pr_.Material = mm_.Material AND pr_.UMP = mm_.UMA
            LEFT JOIN Unicos_cfg_fecha_entrega AS cfg
            ON pr_.Destino = cfg.Tienda AND pr_.Material = cfg.Material
            LEFT JOIN maestro AS ma_
            ON pr_.Material = ma_.COD_material
            WHERE pr_.fecha_entrega BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            )
            SELECT OT,clase_documento,fecha_creado,creado_por,CD,Material,Descripcion,Destino,Cantidad_UMP,UMP,fecha_entrega,Cantidad_entregada,
                    Status,cantidad_base,UMB,Importe,fecha_entrega_actualizada,gerencia,unidad_de_negocio
            FROM tabla_final
            ) TO '{ruta_xlsx}'(FORMAT XLSX , HEADER TRUE)
        """)

        print("🦆 Ejecucion Querys en Duckdb Exitoso 🦆")
    except Exception as e:
        print(f"Hubo un error {e}")
    finally:
        conn.close()


