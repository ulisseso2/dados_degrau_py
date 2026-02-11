from typing import Optional, Tuple
from sqlalchemy import text
from conexao.mysql_connector import conectar_mysql_writer


def atualizar_avaliacao_transcricao(
    transcricao_id: Optional[int],
    insight_ia: str,
    evaluation_ia: Optional[int],
) -> Tuple[bool, Optional[str]]:
    if not transcricao_id:
        return False, "transcricao_id ausente"

    engine = conectar_mysql_writer()
    if engine is None:
        return False, "engine MySQL não inicializado"

    query = text(
        """
        UPDATE seducar.opportunity_transcripts
        SET insight_ia = :insight_ia,
            evaluation_ia = :evaluation_ia
        WHERE id = :transcricao_id
        """
    )

    try:
        with engine.begin() as conn:
            result = conn.execute(
                query,
                {
                    "insight_ia": insight_ia,
                    "evaluation_ia": evaluation_ia,
                    "transcricao_id": transcricao_id,
                },
            )
        if result.rowcount > 0:
            return True, None
        return False, "nenhuma linha atualizada"
    except Exception as e:
        return False, str(e)
