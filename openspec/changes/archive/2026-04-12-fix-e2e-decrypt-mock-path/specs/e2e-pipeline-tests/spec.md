## MODIFIED Requirements

### Requirement: E2E decrypt stage mock targets match actual imports
E2E pipeline tests that mock decryption functions SHALL use the exact attribute name imported in `ccas.decryptor.job` — currently `decrypt_pdf_multi`.

#### Scenario: Happy path decrypt mock resolves
- **WHEN** `test_pipeline_happy_path.py::TestDecryptStage` runs
- **THEN** the mock target `ccas.decryptor.job.decrypt_pdf_multi` SHALL resolve without `AttributeError`

#### Scenario: Error path decrypt mock resolves
- **WHEN** `test_pipeline_error_path.py::TestDecryptFailureIsolation` runs
- **THEN** the mock target `ccas.decryptor.job.decrypt_pdf_multi` SHALL resolve without `AttributeError`
