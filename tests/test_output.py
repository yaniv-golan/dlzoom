"""
Tests for output formatting, specifically success icon display
"""

from unittest.mock import MagicMock

from dlzoom.output import OutputFormatter


class TestSuccessIconDisplay:
    """Test that success messages display checkmark icon"""

    def test_success_displays_checkmark(self):
        """Success message should display checkmark (✓) icon"""
        formatter = OutputFormatter()

        # Mock the console after formatter is created
        mock_console = MagicMock()
        formatter.console = mock_console

        # Call output_success method
        formatter.output_success("Operation completed")

        # Verify console.print was called
        assert mock_console.print.called

        # Get the printed message
        call_args = mock_console.print.call_args[0][0]

        # Should contain checkmark
        assert "✓" in call_args
        assert "Operation completed" in call_args

    def test_success_uses_green_color(self):
        """Success message should use green color"""
        formatter = OutputFormatter()

        mock_console = MagicMock()
        formatter.console = mock_console

        formatter.output_success("Test message")

        call_args = mock_console.print.call_args[0][0]

        # Should contain green markup
        assert "[bold green]" in call_args

    def test_success_not_empty_icon(self):
        """Success message should not have empty icon space"""
        formatter = OutputFormatter()

        mock_console = MagicMock()
        formatter.console = mock_console

        formatter.output_success("Test")

        call_args = mock_console.print.call_args[0][0]

        # Should NOT have empty space after color tag
        # Old bug: "[bold green][/bold green] message"
        # Fixed: "[bold green]✓[/bold green] message"
        assert not call_args.startswith("[bold green][/bold green]")
        assert "✓" in call_args


class TestOtherOutputMethods:
    """Test other output formatting methods"""

    def test_error_displays_correctly(self):
        """Error message should display with appropriate formatting"""
        formatter = OutputFormatter()

        mock_console = MagicMock()
        formatter.console = mock_console

        formatter.output_error("Error occurred")

        assert mock_console.print.called
        call_args = mock_console.print.call_args[0][0]
        assert "Error occurred" in call_args

    def test_info_displays_correctly(self):
        """Info message should display with appropriate formatting"""
        formatter = OutputFormatter()

        mock_console = MagicMock()
        formatter.console = mock_console

        formatter.output_info("Information")

        assert mock_console.print.called
        call_args = mock_console.print.call_args[0][0]
        assert "Information" in call_args

    def test_silent_mode_suppresses_output(self):
        """Silent mode should suppress all output"""
        formatter = OutputFormatter()

        mock_console = MagicMock()
        formatter.console = mock_console

        formatter.set_silent(True)

        formatter.output_success("Should not print")
        formatter.output_error("Should not print")
        formatter.output_info("Should not print")

        # Console.print should not be called in silent mode
        assert not mock_console.print.called


class TestSilentContextManager:
    """Tests for OutputFormatter.capture_silent context manager"""

    def test_capture_silent_restores_state(self):
        formatter = OutputFormatter()
        formatter.set_silent(False)

        with formatter.capture_silent():
            assert formatter.silent is True

        assert formatter.silent is False

    def test_capture_silent_respects_previous_true(self):
        formatter = OutputFormatter()
        formatter.set_silent(True)

        with formatter.capture_silent():
            assert formatter.silent is True

        assert formatter.silent is True

    def test_capture_silent_custom_flag(self):
        formatter = OutputFormatter()
        formatter.set_silent(True)

        with formatter.capture_silent(enabled=False):
            assert formatter.silent is False

        assert formatter.silent is True


class TestJSONMode:
    """Test JSON output mode"""

    def test_json_mode_success(self):
        """JSON mode should output structured JSON for success"""
        formatter = OutputFormatter(mode="json")

        # Just verify it doesn't crash - actual JSON output goes to stdout
        formatter.output_success("Test message")

    def test_json_mode_error(self):
        """JSON mode should output structured JSON for errors"""
        formatter = OutputFormatter(mode="json")

        # Just verify it doesn't crash
        formatter.output_error("Error message")
