from .chapter_splitter_executor import ChapterSplitterExecutor
from .timeline_fixer_executor import TimelineFixerExecutor
from .setting_recorder_executor import SettingRecorderExecutor
from .context_builder_executor import ContextBuilderExecutor
from .draft_generator_executor import DraftGeneratorExecutor
from .draft_reviewer_executor import DraftReviewerExecutor
from .draft_polisher_executor import DraftPolisherExecutor
from .fact_recorder_executor import FactRecorderExecutor
from .task_archiver_executor import TaskArchiverExecutor
from .init_executor import InitExecutor
from .character_builder_executor import CharacterBuilderExecutor
from .plan_executor import PlanExecutor
from .query_executor import QueryExecutor
from .story_system_executor import StorySystemExecutor
from .foreshadow_cool_point_extractor_executor import ForeshadowCoolPointExtractorExecutor
from .chapter_plot_generator_executor import ChapterPlotGeneratorExecutor
from .chapter_plot_reviewer_executor import ChapterPlotReviewerExecutor

EXECUTORS = [
    ChapterSplitterExecutor,
    TimelineFixerExecutor,
    SettingRecorderExecutor,
    ContextBuilderExecutor,
    ChapterPlotGeneratorExecutor,
    ChapterPlotReviewerExecutor,
    DraftGeneratorExecutor,
    DraftReviewerExecutor,
    DraftPolisherExecutor,
    FactRecorderExecutor,
    TaskArchiverExecutor,
    InitExecutor,
    CharacterBuilderExecutor,
    PlanExecutor,
    QueryExecutor,
    StorySystemExecutor,
    ForeshadowCoolPointExtractorExecutor,
]