-- Ejecutar una vez en la base PostgreSQL de megaSip antes del despliegue.
-- También admite una tabla de archivadas creada previamente.
BEGIN;

CREATE TABLE IF NOT EXISTS public.cenefas_archivadas (
    LIKE public.cenefas INCLUDING CONSTRAINTS
);

ALTER TABLE public.cenefas_archivadas
    ADD COLUMN IF NOT EXISTS fecha_archivado timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS usuario_archivado text;

-- El ID original se conserva; no se comparte la secuencia de cenefas.
CREATE UNIQUE INDEX IF NOT EXISTS cenefas_archivadas_id_uq
    ON public.cenefas_archivadas (id);
CREATE INDEX IF NOT EXISTS cenefas_archivadas_fecha_idx
    ON public.cenefas_archivadas (fecha_archivado DESC, id DESC);
CREATE INDEX IF NOT EXISTS cenefas_archivadas_tipo_vigencia_idx
    ON public.cenefas_archivadas (tipo_cenefa, desde, hasta);

COMMIT;
