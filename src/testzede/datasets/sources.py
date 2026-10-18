"""İndirilebilir veri setlerinin kaynakları.

Her dosya Hugging Face'te sabit bir revizyona (commit) ve SHA-256 özetine
bağlanır; böylece herkes birebir aynı veriyle çalışır ve deneyler tekrarlanabilir.
67_Python_Code_Small ders sorumlusundan alınır, indirilmez.
"""

from __future__ import annotations

from dataclasses import dataclass

HF_BASE_URL = "https://huggingface.co"


@dataclass(frozen=True)
class RemoteFile:
    """Uzak depodaki tek bir veri dosyası."""

    repo_id: str
    revision: str
    remote_path: str
    local_name: str
    sha256: str

    def url(self, base_url: str = HF_BASE_URL) -> str:
        """Dosyanın sabit revizyondaki indirme adresi."""
        return f"{base_url}/datasets/{self.repo_id}/resolve/{self.revision}/{self.remote_path}"


_HUMANEVAL_REPO = "openai/openai_humaneval"
_HUMANEVAL_REV = "7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544"
_LITE_REPO = "kjain14/testgenevallite"
_LITE_REV = "15321b4dea8a26ce80f1c29c6b7ea8f64a82a943"
_FULL_REPO = "kjain14/testgeneval"
_FULL_REV = "b1d85082bcedf9cc3bfde4191f912c20bd2ab428"

SOURCES: dict[str, tuple[RemoteFile, ...]] = {
    "humaneval": (
        RemoteFile(
            _HUMANEVAL_REPO,
            _HUMANEVAL_REV,
            "openai_humaneval/test-00000-of-00001.parquet",
            "test.parquet",
            "2f2871a15fbc95b6c683043359f4ed8e144c5a1c4f24f25f66bc51f598dfcfb6",
        ),
    ),
    "testgeneval-lite": (
        RemoteFile(
            _LITE_REPO,
            _LITE_REV,
            "data/test-00000-of-00001.parquet",
            "test.parquet",
            "63d6943b6d9f7515fb49b11888f948905b7242a9546eff649b42f20697146c17",
        ),
        RemoteFile(
            _LITE_REPO,
            _LITE_REV,
            "data/dev-00000-of-00001.parquet",
            "dev.parquet",
            "0b9cd9da446135632e3b1ea57bb438b025cdc13a7633816a4f48ae41ba0985d7",
        ),
    ),
    # Ana deney yalnızca test bölümünü kullanır; train (~600 MB) indirilmez.
    "testgeneval": (
        RemoteFile(
            _FULL_REPO,
            _FULL_REV,
            "data/test-00000-of-00001.parquet",
            "test.parquet",
            "3bb294497160d03f355ccc81512c9dd03186475ed52bb67d35b0f4f2365ad64b",
        ),
    ),
}
