from .base_repository import init_db, close, _get_conn, _lock
from .ebook_interface_repository import (
    upsert_interface, get_interfaces, get_interface, update_interface_status,
    set_interface_active, delete_interface, get_interfaces_by_site
)
from .ebook_library_repository import (
    add_ebook, get_ebook, get_ebook_by_md5, get_ebooks_paged, update_ebook, delete_ebook
)
from .ebook_chapter_repository import add_chapters, get_chapters, get_chapter, get_chapter_count
from .script_repository import (
    add_script, get_script, get_scripts_by_book, get_scripts_by_task_id, update_script, delete_script
)
from .script_chapter_repository import (
    add_script_chapters, get_script_chapters_all, get_script_chapter, get_script_chapter_count,
    update_script_chapter, delete_script_chapter, get_max_chapter_index
)
from .script_line_repository import (
    add_script_lines, insert_line_at_position, reorder_script_lines, get_script_lines,
    get_script_lines_paged, update_script_line, delete_script_line, delete_script_lines_by_chapter,
    delete_script_lines, get_script_line_by_id, get_script_line_count, get_script_chapters_with_lines
)
from .script_character_repository import (
    get_character_configs, get_character_config, upsert_character_config, add_script_characters,
    get_script_characters, increment_character_line_count, delete_script_characters
)
from .audio_history_repository import (
    save_audio_history, get_audio_history_by_line_id, get_matching_audio_history,
    get_audio_history_by_id, save_chapter_audio_history, get_chapter_audio_history,
    get_chapter_audio_history_by_id
)
from .audio_cache_repository import get_audio_cache, save_audio_cache
from .chapter_sentence_repository import add_chapter_sentences, get_chapter_sentences, get_chapter_sentence_count
from .capability_test_repository import (
    add_capability_test, get_capability_tests_paged, get_capability_test, delete_capability_test,
    delete_all_capability_tests
)

from .writing_tasks_repository import (
    add_writing_task, get_writing_tasks, get_writing_task, update_writing_task,
    delete_writing_task, get_running_tasks
)
from .chapter_versions_repository import (
    add_chapter_version, get_chapter_versions, get_chapter_version_detail,
    delete_chapter_versions, delete_chapter_version, get_chapter_version_count
)
