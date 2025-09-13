# VoiceTray

**Expand your words, save your thoughts.**

A Python application that runs in the system tray and converts speech to text, inserting it into any active input field when a hotkey is pressed or saving it to text files.

## Features

- **System Tray Integration**: Minimizes to system tray for easy access
- **Global Hotkey**: Press `F9` to start speech recognition
- **Universal Text Input**: Works with any application's input fields
- **Offline Speech Recognition**: Uses Vosk for instant, network-free recognition
- **Online Fallback**: Falls back to Google's speech recognition if offline model unavailable
- **Smart Text Processing**: 
  - **Repetition Detection**: Automatically removes duplicate words and phrases
  - **Grammar Checking**: Applies basic grammar corrections and capitalization
  - **Similarity Filtering**: Prevents processing of nearly identical repeated inputs
- **Text File Storage**: Save recognized texts to simple text files
- **Text Expansion**: Support for custom snippets that expand trigger words into full text
- **Configurable Settings**: Customize hotkeys and startup options via settings.txt
- **Simple Controls**: Start/stop listening via tray menu

## Installation

### Prerequisites

- Python 3.7 or higher
- Microphone access
- Internet connection (for Google Speech Recognition)

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Install PyAudio (Windows)

If you encounter issues with PyAudio installation on Windows, try:

```bash
pip install pipwin
pipwin install pyaudio
```

Alternatively, download the appropriate `.whl` file from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) and install it:

```bash
pip install PyAudio-0.2.11-cp39-cp39-win_amd64.whl
```

## Usage

### Starting the Application

**Option 1: Using the batch file (Recommended)**
1. Double-click `run_app.bat`
2. The application will start in background mode
3. You can safely close the console window after startup

**Option 2: Command line**
1. For background mode: `pythonw speech_to_text_app.py`
2. For console mode: `python speech_to_text_app.py`

**After starting:**
- The application will minimize to the system tray (look for a microphone icon)
- The application automatically starts listening when launched
- **Important**: The app runs independently - you can close the Python file/console window

### Using Speech-to-Text

1. Click on any input field in any application (text editor, browser, chat app, etc.)
2. Press `F9` to start recording
3. Speak clearly into your microphone (recording lasts up to 5 seconds)
4. The recognized text will be automatically typed into the active input field

### Alternative: Save to Database
1. Press `F10` to record speech and save directly to database
2. A temporary notification will show what was saved
3. Access saved texts via the system tray menu

### Tray Menu Options

VoiceTray provides a system tray icon with the following options:
- **Start Listening**: Activates the speech recognition hotkey
- **Stop Listening**: Deactivates the speech recognition hotkey
- **Settings**: View current hotkey (more options coming soon)
- **Quit**: Exit the application

## Text Storage and Processing

### Saving Texts
- Use **F10** to record speech and save directly to text files
- Shows temporary notification with saved text preview
- Each saved text includes timestamp and source information
- Texts are automatically processed (repetition removal, grammar checking) before saving
- No text is typed to screen when using F10 (save-only mode)

### Text Processing Features
VoiceTray stores all recognized text in simple text files with timestamps and source information. Text processing includes:

- **Grammar Enhancement**: Basic grammar corrections and capitalization
- **Repetition Removal**: Eliminates repeated phrases and words
- **Similarity Detection**: Prevents saving nearly identical text entries
- **Text Expansion**: Automatically expands predefined snippets from snippets.txt
- **Configurable Settings**: Customize hotkeys and behavior via settings.txt

## Troubleshooting

### Common Issues

1. **No microphone detected**:
   - Ensure your microphone is connected and working
   - Check Windows privacy settings for microphone access
   - Try running the application as administrator

2. **Speech recognition not working**:
   - Check your internet connection
   - Ensure you're speaking clearly and loudly enough
   - Try adjusting microphone sensitivity in Windows settings

3. **Hotkey not responding**:
   - Make sure "Start Listening" is enabled in the tray menu
   - Check if another application is using the F9 key
   - Try running the application as administrator

4. **Application exits when closing console**:
   - Use `pythonw speech_to_text_app.py` instead of `python`
   - Or use the provided `run_app.bat` file
   - The app is designed to run independently in the background

4. **Text not inserting**:
   - Ensure the target input field is active (cursor blinking)
   - Some applications may block automated text input
   - Try clicking in the input field before using the hotkey

### Error Messages

- **"Error with speech recognition service"**: Check internet connection
- **"Could not understand audio"**: Speak more clearly or adjust microphone
- **"No speech detected"**: Ensure microphone is working and speak louder

## Text Processing Features

### Repetition Detection
The application automatically detects and removes:
- **Consecutive duplicate words**: "the the cat" → "the cat"
- **Repeated phrases**: "hello world hello world" → "hello world"
- **Similar recent inputs**: Prevents processing nearly identical text within recent history

### Grammar Checking
Basic grammar corrections include:
- **Capitalization**: First letter of sentences
- **Contractions**: "cant" → "can't", "im" → "I'm", "wont" → "won't"
- **Pronoun correction**: "i" → "I"
- **Punctuation spacing**: Proper spacing around commas, periods, etc.

### Processing Output
When text is processed, you'll see console output showing:
```
Original: hello hello world i cant do this
Processed: Hello world I can't do this
```

## Technical Details

### Dependencies

- `speechrecognition`: Google Speech Recognition API (fallback)
- `vosk`: Offline speech recognition
- `sounddevice`: Direct audio capture for offline recognition
- `pystray`: System tray functionality
- `keyboard`: Global hotkey detection
- `pyautogui`: Text insertion
- `Pillow`: Icon image creation
- `pyaudio`: Microphone audio capture (online mode)

### Default Hotkey

- **Windows**: `F9`
- The hotkey can be customized by modifying the `self.hotkey` variable in the code

### Privacy Note

This application primarily uses offline speech recognition (Vosk), which means your audio is processed locally on your machine without being sent to external servers. If the offline model is unavailable, it falls back to Google's Speech Recognition service. No audio is stored locally by this application.

## Future Enhancements

- Customizable hotkeys through settings menu
- Additional offline language models
- Advanced grammar and spell checking
- Voice commands for text formatting
- Audio recording indicators
- Configuration file for settings
- Custom vocabulary and domain-specific terms

## License

This project is open source. Feel free to modify and distribute as needed.

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Ensure all dependencies are properly installed
3. Try running the application from command line to see error messages
4. Verify microphone permissions in Windows settings