# Every bug so far, and what stops it coming back

Each row is a bug that really happened, the test (or guard in the code) that fails if it
returns, and where to find it. `python -m pytest` runs them all; it also runs before every
commit (git pre-commit hook). `python scripts/mutation_check.py` puts the most damaging
ones back into the code one at a time and checks that a test fails for each.

| # | Bug | Guarded by |
|---|-----|-----------|
| 1 | "开始聆听" did nothing under pythonw (stdout was None) | `test_regressions::test_pythonw_without_a_console_still_logs` |
| 2 | Starting right after pausing was lost | `test_engine::test_start_right_after_pause_still_starts` |
| 3 | One failed command stopped listening | run loop catches per command (`app.Assistant.run`) |
| 4 | Buttons stayed disabled after a click | app.js keeps the button element, not `event.currentTarget` |
| 5 | Unclear AI provider errors (402, quota, paid-only models) | `test_ai::test_*_explained`, `test_openai_bad_key_is_spoken` |
| 6 | Relaunching WeChat opened its login window | `test_messaging::test_running_app_is_brought_forward_not_relaunched`, `test_daily::test_wechat_in_the_tray_*` |
| 7 | Startup deadlock restyling our own windows from a thread | `test_regressions::test_restyling_our_windows_never_uses_pywin32` |
| 8 | Flashing taskbar icon; bubble showing itself on load | `test_regressions::test_orb_and_bubble_never_get_a_taskbar_button_*` |
| 9 | Qwen3-ASR wouldn't unpack ("Paths don't have the same drive") | `test_regressions::test_model_download_unpacks_*` |
| 10 | Wake on "图灵" in the middle of a sentence | `test_regressions::test_name_mid_sentence_does_not_wake` |
| 11 | Sentence cut at the pause after "然后" | `test_regressions::test_a_pause_after_then_does_not_cut_the_sentence` |
| 12 | Old wake settings broke after the sensitivity change | `test_commands::test_old_wake_settings_are_upgraded` |
| 13 | Orb on a grey square; then clicks fell through it | `test_regressions::test_orb_background_is_glass_not_a_colour_key` |
| 14 | Main window: ERR_FILE_NOT_FOUND ("?background") | `test_regressions::test_main_page_address_has_no_query` |
| 15 | Closing the main window froze Turing | `test_control_center::test_closing_the_main_window_never_waits_for_its_page` |
| 16 | Settings and persona pages couldn't scroll | `test_regressions::test_long_pages_scroll` |
| 17 | Page code used elements that no longer existed | `test_regressions::test_page_script_only_uses_elements_that_exist` |
| 18 | Chinese left over in English mode | `test_regressions::test_every_chinese_text_on_the_pages_has_an_english_version` |
| 19 | Chrome stopped at "Who's using Chrome?" | `test_fixes::test_chrome_without_profile_opens_the_last_used`, `test_browsers` |
| 20 | AI typed into Turing's own bubble and pressed Enter | `test_regressions::test_keys_never_go_into_turings_own_window` |
| 21 | Search typed into whatever window was in front (Claude) | `test_sites::test_no_typing_into_another_window_after_opening_an_app` |
| 22 | Editing keys pressed in the wrong window | `test_daily::test_editing_keys_wait_for_the_app_just_opened` |
| 23 | AI said it did things it didn't | `test_fixes::test_claimed_success_*`, `test_claims_with_words_in_between_are_caught` |
| 24 | AI made up an exchange rate; asked ChatGPT unasked | `test_regressions::test_ai_must_not_state_unfounded_facts_*` |
| 25 | Asking ChatGPT went to the weather skill | `test_fixes::test_ask_a_chatbot` |
| 26 | "ChatGPT" heard as 叉GPT / I G P T | `test_fixes::test_chatgpt_heard_right` |
| 27 | A correction while confirming cancelled the message | `test_fixes::test_corrected_message_is_confirmed_again` |
| 28 | "Where are you" in a message heard as "不要语" | `test_regressions::test_messages_are_rechecked_by_the_accurate_recognizer` |
| 29 | Brightness request changed the volume | `test_abilities::test_volume_words_are_not_brightness` |
| 30 | QQ message sent through WeChat | `test_regressions::test_qq_requests_never_go_out_on_wechat` |
| 31 | Video call request sent as a WeChat text | `test_abilities::test_a_call_request_never_becomes_a_text` |
| 32 | "奥克维尔周末" taken as a city | `test_abilities::test_weather_city_without_time_words` |
| 33 | "这周天气" answered with Sunday only | `test_regressions::test_this_week_is_not_sunday` |
| 34 | "open notepad" didn't find 记事本 | `test_regressions::test_english_names_find_windows_own_apps` |
| 35 | Volume from the AI failed (COM not set up in the thread) | `volume._endpoint` calls `CoInitialize` |
| 36 | Maximize crashed (win32gui has no IsZoomed) | `test_regressions::test_window_actions_use_calls_that_exist` |
| 37 | Notes failed to save ("different drive") | `test_regressions::test_saving_works_when_windows_refuses_the_swap` |
| 38 | "现在是几月几号" not understood | `test_regressions::test_date_question_with_xianzai` |
| 39 | Alarm listed as "16小时23分钟4秒" | `test_regressions::test_alarms_are_listed_by_their_time` |
| 40 | Unrelated sentence counted as "yes": message sent to Mom | `test_fixes::test_only_a_clear_yes_sends` |
| 41 | Alt tap: windows swallowed the next key | `test_regressions::test_bringing_a_window_forward_does_not_tap_alt` |
| 42 | Typing wiped a copied image or file | `test_regressions::test_typing_leaves_the_clipboard_alone` |
| 43 | WeChat froze when opened from the tray | `test_daily::test_hidden_windows_are_never_shown_from_outside`, `test_wechat_in_the_tray_*` |
| 44 | Interrupting Turing almost never worked | `test_bargein` (6 tests) |
| 45 | Microphone dead after unplugging / new default / sleep | `test_audio` (6 tests) |
| 46 | Mic audio could pile up without limit | `test_audio::test_queue_is_bounded` |
| 47 | numpy reserved ~750 MB | `test_regressions::test_numpy_does_not_reserve_memory_per_cpu_thread` |
| 48 | Old Qwen3 copy kept in memory after a restart | `test_regressions::test_big_recognizer_is_let_go_when_listening_stops` |
| 49 | Qwen3 loaded on top of a full memory | `test_fixes::test_accurate_recognizer_not_loaded_when_memory_is_low` |
| 50 | Live words flooded the conversation log | `test_engine::test_live_words_are_shown_but_not_logged` |
| 51 | Two Ollama servers fought for the port | `test_regressions::test_ollama_is_not_started_twice` |
| 52 | Downloaded programs could be run by voice | `test_abilities::test_downloaded_programs_are_never_run` |
| 53 | Shutdown without asking | `test_abilities::test_shutdown_asks_first_and_can_be_declined` |
| 54 | Two Turing copies with different settings (app-package AppData) | settings merged; Turing started outside the Claude app; saving via `paths.write_text_safely` |
| 55 | Dry run really muted the PC, changed the voice, read the clipboard | `test_regressions::test_dry_run_harness_changes_nothing_real` |
| 56 | A test pressed real keys and hid WeChat | `tests/conftest.py` (no real keys in any test) |
| 57 | `notes.list` shadowed `list`; `info` used names before defining them | importing every skill (`test_ai::test_skill_tools_are_well_formed`) |
| 58 | Douyin search typed nowhere useful | `test_sites::test_douyin_search_opens_results_and_says_where` |
| 59 | English PC-status questions cut off | `test_daily::test_pc_status_words` |
| 60 | Weather questions opened the browser | `test_weather::test_weather_never_opens_the_browser` |
| 61 | With openai 3.39 (a fresh install), a paid-plan model was reported as "out of credit" | `test_regressions::test_provider_error_text_is_found_whatever_the_sdk_version` |
| 62 | README examples (亮度调高, 连上蓝牙耳机, 春节还有几天, 100美元换人民币) not understood | `test_regressions::test_everyday_wordings_from_the_readme_are_understood` |
| 63 | The translation test stopped checking after any `translate="no"` tag but `<option>` | `test_regressions::_Texts` keeps a stack of those tags |
| 64 | `python -m turing --text` crashed at the end of piped input | `__main__` catches EOFError |
| 65 | No way to get the optional Qwen3-ASR model on a new install | `python -m turing.models qwen3-asr`; the settings page says so |
| 66 | English questions turned away by length limits sized for Chinese (battery, news); "next desktop", "what's the date next Friday" not understood; English news fetch got a web page | `test_regressions::test_english_questions_as_long_as_the_chinese_ones_are_understood` |
| 67 | English replies said "Opening 记事本", "B站", "call you alex" | `test_regressions::test_english_replies_use_english_names` |

Not caused by Turing, fixed on the PC: the AMD driver memory leak, and Ollama's model folder
pointing at an unwritable place (its server restarted every second).
