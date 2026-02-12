import argparse
from typing import Optional
from sqlalchemy import text

from conexao.mysql_connector import conectar_mysql
from utils.transcricao_mysql_writer import atualizar_avaliacao_transcricao


def buscar_avaliacoes_pendentes(limite: int, transcricao_id: Optional[int] = None):
    engine = conectar_mysql()
    if engine is None:
        raise RuntimeError("Engine de leitura não inicializado")

    base_query = """
        SELECT
            ot.id AS transcricao_id,
            ot.created_at AS created_at,
            ot.insight_ia AS insight_ia,
            ot.evaluation_ia AS evaluation_ia
        FROM seducar.opportunity_transcripts ot
        LEFT JOIN seducar.transcription_ai_summaries tas
            ON ot.id = tas.transcription_id
        WHERE ot.insight_ia IS NOT NULL
          AND ot.insight_ia <> ''
          AND tas.transcription_id IS NULL
    """

    params = {}
    if transcricao_id is not None:
        base_query += " AND ot.id = :transcricao_id"
        params["transcricao_id"] = transcricao_id

    base_query += " ORDER BY ot.id ASC LIMIT :limite"
    params["limite"] = limite

    with engine.begin() as conn:
        result = conn.execute(text(base_query), params)
        return result.fetchall()


def main():
    parser = argparse.ArgumentParser(description="Backfill transcription_ai_summaries")
    parser.add_argument("--limit", type=int, default=1, help="Quantidade de registros a migrar")
    parser.add_argument("--transcricao-id", type=int, help="Filtrar por um ID específico")
    args = parser.parse_args()

    registros = buscar_avaliacoes_pendentes(args.limit, args.transcricao_id)
    if not registros:
        print("Nenhum registro pendente encontrado.")
        return

    sucesso = 0
    falhas = 0

    for row in registros:
        transcricao_id = row.transcricao_id
        insight_ia = row.insight_ia
        evaluation_ia = row.evaluation_ia
        created_at = row.created_at

        atualizado, erro = atualizar_avaliacao_transcricao(
            transcricao_id=transcricao_id,
            insight_ia=insight_ia,
            evaluation_ia=evaluation_ia,
            created_at=created_at,
        )

        if atualizado:
            sucesso += 1
            print(f"OK: transcricao_id={transcricao_id}")
        else:
            falhas += 1
            print(f"ERRO: transcricao_id={transcricao_id} ({erro})")

    print(f"Concluído: {sucesso} sucesso(s), {falhas} falha(s).")


if __name__ == "__main__":
    main()
