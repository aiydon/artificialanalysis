from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Group = Literal["llm", "image", "video", "speech", "music", "agents", "hardware", "other"]
Mode = Literal["array", "values", "tables", "path"]


class Source(BaseModel):
    """A dataset embedded in one page's Next.js flight payload.

    mode=array   read the JSON arrays stored under ``props`` (leaderboards, catalogs)
    mode=values  scan the payload for arena rows of ``{formatted, values}`` and take
                 the largest ranking (the "all models" slice)
    mode=path    read the object under ``props[0]`` and follow ``unwrap`` to an array
    """

    model_config = ConfigDict(frozen=True)

    dataset: str
    group: Group
    label: str
    path: str
    props: tuple[str, ...] = ()
    mode: Mode = "array"
    key: tuple[str, ...]
    unwrap: str | None = None
    task_field: bool = False
    choose: Literal["first", "largest"] = "first"
    dashboard: bool = True
    primary: bool = False

    @model_validator(mode="after")
    def _check_mode(self) -> Source:
        if self.mode in ("values", "tables"):
            if self.props:
                raise ValueError(f"{self.dataset}: {self.mode} mode takes no props")
            return self
        if not self.props:
            raise ValueError(f"{self.dataset}: props are required for mode {self.mode}")
        if self.mode == "path" and (len(self.props) != 1 or not self.unwrap):
            raise ValueError(f"{self.dataset}: path mode needs one prop and an unwrap path")
        return self


def _src(
    dataset: str,
    group: Group,
    label: str,
    path: str,
    props: tuple[str, ...] = (),
    *,
    key: tuple[str, ...],
    mode: Mode = "array",
    unwrap: str | None = None,
    task_field: bool = False,
    choose: Literal["first", "largest"] = "first",
    dashboard: bool = True,
    primary: bool = False,
) -> Source:
    return Source(
        dataset=dataset,
        group=group,
        label=label,
        path=path,
        props=props,
        mode=mode,
        key=key,
        unwrap=unwrap,
        task_field=task_field,
        choose=choose,
        dashboard=dashboard,
        primary=primary,
    )


SOURCES: tuple[Source, ...] = (
    # --- language models -------------------------------------------------
    _src(
        "llm_models",
        "llm",
        "Language model leaderboard",
        "/leaderboards/models",
        ("initialModels",),
        key=("release.slug", "suffix"),
        primary=True,
    ),
    _src(
        "llm_providers",
        "llm",
        "API provider endpoints",
        "/leaderboards/providers",
        ("initialRows",),
        key=("host.slug", "hostApiId", "model.release.slug", "label"),
    ),
    _src(
        "llm_releases",
        "llm",
        "Model releases",
        "/leaderboards/models",
        ("releases",),
        key=("slug",),
    ),
    _src(
        "llm_hosts",
        "llm",
        "Language model hosts",
        "/leaderboards/models",
        ("hosts",),
        key=("slug",),
    ),
    _src(
        "evaluations",
        "llm",
        "Evaluation catalog",
        "/evaluations",
        ("evaluations",),
        key=("slug",),
    ),
    _src(
        "capability_indexes",
        "llm",
        "Capability indexes",
        "/leaderboards/models",
        ("capabilityIndexes",),
        key=("capability",),
    ),
    _src(
        "decision_models",
        "llm",
        "Decision model catalog",
        "/leaderboards/models",
        ("decisionModels",),
        key=("slug",),
    ),
    _src(
        "chatbot_apps",
        "llm",
        "Chatbot app catalog",
        "/leaderboards/models",
        ("chatbots",),
        key=("slug",),
        choose="largest",
    ),
    _src(
        "coding_agents_catalog",
        "llm",
        "Coding agent catalog",
        "/leaderboards/models",
        ("codingAgents",),
        key=("slug",),
    ),
    _src(
        "search_api_providers",
        "llm",
        "Search API provider catalog",
        "/leaderboards/models",
        ("searchApiProviders",),
        key=("slug",),
    ),
    _src(
        "image_model_families",
        "image",
        "Image model families",
        "/leaderboards/models",
        ("imageModelFamilies",),
        key=("slug",),
    ),
    _src(
        "video_model_families",
        "video",
        "Video model families",
        "/leaderboards/models",
        ("videoModelFamilies",),
        key=("slug",),
    ),
    _src(
        "stt_model_families",
        "speech",
        "Speech-to-text model families",
        "/leaderboards/models",
        ("sttModelFamilies",),
        key=("slug",),
    ),
    _src(
        "tts_model_families",
        "speech",
        "Text-to-speech model families",
        "/leaderboards/models",
        ("textToSpeechModelFamilies",),
        key=("slug",),
    ),
    # --- capability indexes ---------------------------------------------
    _src(
        "index_economics",
        "llm",
        "Economics index",
        "/indexes/economics",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    _src(
        "index_engineering",
        "llm",
        "Engineering index",
        "/indexes/engineering",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    _src(
        "index_finance",
        "llm",
        "Finance & accounting index",
        "/indexes/finance-and-accounting",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    _src(
        "index_healthcare",
        "llm",
        "Healthcare & medical index",
        "/indexes/healthcare-and-medical",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    _src(
        "index_legal",
        "llm",
        "Legal index",
        "/indexes/legal",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    _src(
        "index_strategy",
        "llm",
        "Strategy & ops index",
        "/indexes/strategy-and-ops",
        ("initialModels",),
        key=("slug", "suffix"),
    ),
    # --- image -----------------------------------------------------------
    _src(
        "image_models",
        "image",
        "Image model leaderboard",
        "/image/models",
        ("textToImage", "imageEditing"),
        key=("slug",),
        task_field=True,
        primary=True,
    ),
    _src(
        "image_host_models",
        "image",
        "Image API endpoints",
        "/image/models",
        ("allHostModels",),
        key=("id",),
    ),
    _src(
        "image_tags",
        "image",
        "Image arena tags",
        "/image/leaderboard/text-to-image",
        ("tags",),
        key=("slug",),
    ),
    _src(
        "image_arena_t2i",
        "image",
        "Image arena: text-to-image",
        "/image/leaderboard/text-to-image",
        key=("id",),
        mode="values",
    ),
    _src(
        "image_arena_t2i_slices",
        "image",
        "Image arena: all text-to-image slices",
        "/image/leaderboard/text-to-image",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "image_arena_editing",
        "image",
        "Image arena: editing",
        "/image/leaderboard/editing",
        key=("id",),
        mode="values",
    ),
    # --- video -----------------------------------------------------------
    _src(
        "video_models",
        "video",
        "Video model leaderboard",
        "/video/models",
        (
            "textToVideo",
            "imageToVideo",
            "videoToVideo",
            "textToVideoAudio",
            "imageToVideoAudio",
            "videoToVideoAudio",
        ),
        key=("slug",),
        task_field=True,
        primary=True,
    ),
    _src(
        "video_host_models",
        "video",
        "Video API endpoints",
        "/video/models",
        ("allHostModels",),
        key=("id",),
    ),
    _src(
        "video_tags",
        "video",
        "Video arena tags",
        "/video/leaderboard/text-to-video",
        ("tags",),
        key=("slug",),
    ),
    _src(
        "image_arena_editing_slices",
        "image",
        "Image arena: all editing slices",
        "/image/leaderboard/editing",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "video_arena_t2v",
        "video",
        "Video arena: text-to-video",
        "/video/leaderboard/text-to-video",
        key=("id",),
        mode="values",
    ),
    _src(
        "video_arena_t2v_slices",
        "video",
        "Video arena: all text-to-video slices",
        "/video/leaderboard/text-to-video",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "video_arena_i2v",
        "video",
        "Video arena: image-to-video",
        "/video/leaderboard/image-to-video",
        key=("id",),
        mode="values",
    ),
    _src(
        "video_arena_i2v_slices",
        "video",
        "Video arena: all image-to-video slices",
        "/video/leaderboard/image-to-video",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "video_arena_editing",
        "video",
        "Video arena: video editing",
        "/video/leaderboard/video-editing",
        key=("id",),
        mode="values",
    ),
    # --- speech ----------------------------------------------------------
    _src(
        "video_arena_editing_slices",
        "video",
        "Video arena: all editing slices",
        "/video/leaderboard/video-editing",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "stt_non_streaming",
        "speech",
        "Speech-to-text (non-streaming)",
        "/speech-to-text/non-streaming",
        ("hostModels", "defaultSelected"),
        key=("id",),
        primary=True,
    ),
    _src(
        "stt_streaming",
        "speech",
        "Speech-to-text (streaming)",
        "/speech-to-text/streaming",
        ("hostModels",),
        key=("id",),
    ),
    _src(
        "tts_models",
        "speech",
        "Text-to-speech leaderboard",
        "/text-to-speech/models",
        ("hostModels",),
        key=("slug",),
    ),
    _src(
        "tts_category_scores",
        "speech",
        "Text-to-speech category scores",
        "/text-to-speech/models",
        ("results",),
        key=("ttsModelId",),
    ),
    _src(
        "tts_arena_controlled",
        "speech",
        "TTS arena: controlled voice",
        "/text-to-speech/leaderboard/controlled-voice",
        key=("id",),
        mode="values",
    ),
    _src(
        "tts_arena_controlled_slices",
        "speech",
        "TTS arena: all controlled-voice slices",
        "/text-to-speech/leaderboard/controlled-voice",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "tts_arena_provider",
        "speech",
        "TTS arena: provider voice",
        "/text-to-speech/leaderboard/provider-voice",
        key=("id",),
        mode="values",
    ),
    _src(
        "tts_accents",
        "speech",
        "TTS accents",
        "/text-to-speech/leaderboard/controlled-voice",
        ("accents",),
        key=("slug",),
    ),
    _src(
        "tts_categories",
        "speech",
        "TTS voice categories",
        "/text-to-speech/leaderboard/controlled-voice",
        ("categories",),
        key=("slug",),
    ),
    _src(
        "tts_arena_provider_slices",
        "speech",
        "TTS arena: all provider-voice slices",
        "/text-to-speech/leaderboard/provider-voice",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "speech_to_speech_models",
        "speech",
        "Speech-to-speech leaderboard",
        "/speech-to-speech",
        ("stsIndexHostModels",),
        key=("id",),
    ),
    _src(
        "speech_to_speech_arena",
        "speech",
        "Speech Agent Arena",
        "/speech-to-speech",
        ("arenaResults",),
        key=("id",),
    ),
    # --- music -----------------------------------------------------------
    _src(
        "music_vocals",
        "music",
        "Music arena: vocals",
        "/music/leaderboard/vocals",
        key=("id",),
        mode="values",
        primary=True,
    ),
    _src(
        "music_vocals_slices",
        "music",
        "Music arena: all vocal slices",
        "/music/leaderboard/vocals",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    _src(
        "music_instrumental",
        "music",
        "Music arena: instrumental",
        "/music/leaderboard/instrumental",
        key=("id",),
        mode="values",
    ),
    _src(
        "music_instrumental_slices",
        "music",
        "Music arena: all instrumental slices",
        "/music/leaderboard/instrumental",
        key=(),
        mode="tables",
        dashboard=False,
    ),
    # --- agents ----------------------------------------------------------
    _src(
        "chatbots_leaderboard",
        "agents",
        "Chatbot leaderboard",
        "/agents/chatbots",
        ("chatbots",),
        key=("id",),
        choose="largest",
        primary=True,
    ),
    _src(
        "coding_agents_leaderboard",
        "agents",
        "Coding agent leaderboard",
        "/agents/coding-agents",
        ("benchmarkRows",),
        key=("id",),
        choose="largest",
    ),
    _src(
        "search_api_leaderboard",
        "agents",
        "Search API leaderboard",
        "/agents/search-api",
        ("searchProviders",),
        key=("id",),
    ),
    # --- hardware --------------------------------------------------------
    _src(
        "hardware_chip_prices",
        "hardware",
        "GPU rental prices",
        "/hardware-inference-stack/datacenter",
        ("chipRentalPrices",),
        key=("id",),
        primary=True,
    ),
    _src(
        "hardware_capacity_runs",
        "hardware",
        "Datacenter capacity tests",
        "/hardware-inference-stack/datacenter",
        ("iterations",),
        key=("id",),
    ),
    _src(
        "hardware_capacity_searches",
        "hardware",
        "Datacenter capacity searches",
        "/hardware-inference-stack/datacenter",
        ("capacitySearches",),
        key=("id",),
    ),
    _src(
        "hardware_laptop_runs",
        "hardware",
        "Laptop / workstation benchmarks",
        "/hardware-inference-stack/laptops-workstations",
        ("runs",),
        key=("id",),
    ),
    _src(
        "hardware_systems",
        "hardware",
        "Benchmarked systems",
        "/hardware-inference-stack/laptops-workstations",
        ("systems",),
        key=("key",),
    ),
    _src(
        "hardware_mobile_measurements",
        "hardware",
        "Mobile device measurements",
        "/hardware-inference-stack/mobile-phones",
        ("measurements",),
        key=("deviceKey", "modelId", "metric", "prefillTokens"),
    ),
    _src(
        "hardware_mobile_models",
        "hardware",
        "Mobile-deployment models",
        "/hardware-inference-stack/mobile-phones",
        ("models",),
        key=("modelId",),
        choose="largest",
    ),
    # --- other -----------------------------------------------------------
    _src(
        "three_d_models",
        "other",
        "3D generation leaderboard",
        "/3d/explorer",
        ("models",),
        key=("id",),
        choose="largest",
        primary=True,
    ),
    _src(
        "three_d_tasks",
        "other",
        "3D benchmark tasks",
        "/3d/explorer",
        ("tasks",),
        key=("id",),
    ),
    _src(
        "three_d_domains",
        "other",
        "3D benchmark domains",
        "/3d/explorer",
        ("domains",),
        key=("id",),
    ),
    _src(
        "three_d_scenes",
        "other",
        "3D benchmark scenes",
        "/3d/explorer",
        ("scenes",),
        key=("id",),
    ),
    _src(
        "microevals",
        "other",
        "Micro-evaluations",
        "/microevals",
        ("microevals",),
        key=("id",),
    ),
    _src(
        "microeval_models",
        "other",
        "Micro-evaluation models",
        "/microevals",
        ("models",),
        key=("id",),
        choose="largest",
    ),
    _src(
        "changelog",
        "other",
        "Changelog events",
        "/changelog",
        ("initialData",),
        key=("id",),
        mode="path",
        unwrap="data",
    ),
)

BY_DATASET = {source.dataset: source for source in SOURCES}


def dataset_names() -> list[str]:
    return [source.dataset for source in SOURCES]


def pages() -> dict[str, list[Source]]:
    """Group sources by URL so each page is downloaded once per run."""
    grouped: dict[str, list[Source]] = {}
    for source in SOURCES:
        grouped.setdefault(source.path, []).append(source)
    return grouped
