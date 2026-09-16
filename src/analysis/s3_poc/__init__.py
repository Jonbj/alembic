"""POC di allineamento al design S3 (#84): A/B pre-registrato su universo PIT.

Codice di ricerca offline: non registra S3 nel registry delle strategie, non
tocca il path ordini e non modifica comportamento in produzione. L'unico seam
esterno e' il runner: manifest congelato + dataset PIT qualificato in,
artefatto decisionale versionato out.
"""
