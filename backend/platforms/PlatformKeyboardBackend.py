"""
Abstract base class for platform-specific keyboard input backends.

This module defines the interface that all platform-specific keyboard backends must implement.
Each platform (Windows, Linux, macOS) can have optimized implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class PlatformKeyboardBackend(ABC):
    """Abstract interface for platform-specific keyboard input."""

    META_KEY_LABEL = "Meta"
    KEY_MAPPING = {}

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the platform-specific keyboard backend.
        
        Returns:
            True if initialization was successful, False otherwise.
        """
        pass

    @abstractmethod
    def shutdown(self):
        """Clean up resources used by the backend."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the backend is available and functional.
        
        Returns:
            True if the backend can be used, False otherwise.
        """
        pass

    @abstractmethod
    def key_down(self, key_code: str) -> bool:
        """
        Press and hold a keyboard key.
        
        Args:
            key_code: Logical key code (e.g., 'left_ctrl', 'a', 'enter')
            
        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def key_up(self, key_code: str) -> bool:
        """
        Release a held keyboard key.
        
        Args:
            key_code: Logical key code
            
        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def tap_key(self, key_code: str) -> bool:
        """
        Press and immediately release a keyboard key.
        
        Args:
            key_code: Logical key code
            
        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def tap_hotkey(self, key_codes: List[str]) -> bool:
        """
        Press multiple keys together as a hotkey, then release.
        
        Args:
            key_codes: List of logical key codes (e.g., ['left_ctrl', 'c'])
            
        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """
        Type a text string.
        
        Args:
            text: Text to type
            
        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def release_all_keys(self):
        """Release any keys currently held by this backend."""
        pass

    @abstractmethod
    def get_failure_reason(self) -> Optional[str]:
        """
        Get a human-readable reason if the backend failed initialization.
        
        Returns:
            Error message, or None if backend is available.
        """
        pass

    @classmethod
    def get_meta_key_label(cls) -> str:
        """Get the user-facing label for the platform meta key."""
        return cls.META_KEY_LABEL
