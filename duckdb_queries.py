import duckdb,os
import polars as pl
from dotenv import load_dotenv
from SAP_ import Descargar_SQ01_OT
from SAP_ import descargar_maestro

load_dotenv()
token = os.getenv("TOKEN_MOTHERDUCK")

def ejecutar_querys(ruta_db,df_zlo_pedi_val:pl.DataFrame ,df_marm:pl.DataFrame ,df_mm60:pl.DataFrame ,fecha_inicio,fecha_fin):

    try:
        conn = duckdb.connect(ruta_db)
        # ACTUALIZAR BASE DE DATOS 
        conn.execute(f""" 
                    DELETE FROM proyectado WHERE fecha_entrega BETWEEN '{fecha_inicio}' AND '{fecha_fin}';
                    INSERT INTO proyectado SELECT * FROM df_zlo_pedi_val;

                    UPDATE proyectado
                    SET tiene_entrega = 'SI'
                    WHERE OT IN (SELECT DISTINCT(OT) FROM proyectado WHERE tiene_entrega = 'SI' );

                    DELETE FROM MARM;
                    INSERT INTO MARM SELECT * FROM df_marm;

                    DELETE FROM MM60;
                    INSERT INTO MM60 SELECT * FROM df_mm60;
                    
                    INSTALL motherduck;
                    LOAD motherduck;
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


        # Actualizar Tabla en Motherduck
        try:
            # conexion a Motherduck
            # os.environ["motherduck_token"] = token
            conn.execute(f""" 
                        SET motherduck_token = "{token}";
                        ATTACH 'md:DB_proyeccion_final'; """)
            

            conn.execute(" BEGIN TRANSACTION; ")
            conn.execute(f""" DELETE FROM DB_proyeccion_final.proyeccion_operativa_diaria 
                            WHERE fecha_entrega BETWEEN '{fecha_inicio}' AND '{fecha_fin}';  """)
            conn.execute(f"""
                INSERT INTO DB_proyeccion_final.proyeccion_operativa_diaria
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
                    COALESCE(m_.Contador,1) AS Contador,
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
                SELECT * FROM tabla_final

            """)
            conn.execute(" COMMIT; ")
            print("🦆 Ejecucion Querys en Motherduck Exitoso 🦆")
        except Exception as e:
            conn.execute(" ROLLBACK; ")
            print(f"Error durante la actualización en Motherduck: {e}")

    except Exception as e:
        print(f"Hubo un error {e}")
    finally:
        conn.close()


