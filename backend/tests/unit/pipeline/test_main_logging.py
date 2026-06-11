"""Pipeline CLI 入口日誌初始化測試（roadmap: logging-init-pipeline-bot）。"""

from unittest.mock import patch

from ccas.pipeline.__main__ import main
from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.summary import PipelineSummary


class TestMainConfiguresLogging:
    def test_main_calls_configure_logging_first(self, capsys):
        """main() 必須先呼叫 configure_logging() 再執行 pipeline。"""
        summary = PipelineSummary(stages=(), total_seconds=0.0)

        with (
            patch("ccas.pipeline.__main__.configure_logging") as mock_configure,
            patch(
                "ccas.pipeline.__main__._parse_args",
                return_value=PipelineOptions(),
            ) as mock_parse,
            patch("ccas.pipeline.__main__._main") as mock_inner,
            patch(
                "ccas.pipeline.__main__.asyncio.run", return_value=summary
            ) as mock_run,
        ):
            main()

        mock_configure.assert_called_once_with()
        mock_run.assert_called_once()
        # configure_logging 先於參數解析與 pipeline 執行
        assert mock_configure.call_count == 1
        assert mock_parse.called
        assert mock_inner.called
        # stdout 仍輸出 JSON 摘要
        out = capsys.readouterr().out
        assert '"total_seconds"' in out
