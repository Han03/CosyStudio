import sqlite3


def _init_schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ebook_interfaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_domain TEXT,
            name TEXT,
            type TEXT,
            url TEXT,
            method TEXT,
            content_type TEXT,
            input_params TEXT,
            output_params TEXT,
            is_active INTEGER DEFAULT 1,
            status TEXT DEFAULT 'untested',
            verified_at REAL,
            last_error TEXT,
            added_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_interfaces_site ON ebook_interfaces(site_domain);
        CREATE INDEX IF NOT EXISTS idx_interfaces_type ON ebook_interfaces(type);
        CREATE INDEX IF NOT EXISTS idx_interfaces_status ON ebook_interfaces(status);

        CREATE TABLE IF NOT EXISTS ebook_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT DEFAULT '',
            file_path TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            word_count INTEGER DEFAULT 0,
            md5 TEXT,
            format TEXT DEFAULT 'txt',
            encoding TEXT DEFAULT 'utf-8',
            description TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_ebook_library_md5 ON ebook_library(md5);
        CREATE INDEX IF NOT EXISTS idx_ebook_library_title ON ebook_library(title);

        CREATE TABLE IF NOT EXISTS ebook_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 1,
            title TEXT DEFAULT '',
            start_pos INTEGER DEFAULT 0,
            end_pos INTEGER DEFAULT 0,
            content TEXT DEFAULT '',
            word_count INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (book_id) REFERENCES ebook_library(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_ebook_chapters_book ON ebook_chapters(book_id);
        CREATE INDEX IF NOT EXISTS idx_ebook_chapters_index ON ebook_chapters(book_id, chapter_index);

        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            chapter_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            description TEXT DEFAULT '',
            task_id TEXT DEFAULT '',
            error TEXT DEFAULT '',
            progress INTEGER DEFAULT 0,
            progress_message TEXT DEFAULT '',
            generating_chapter_index INTEGER DEFAULT 0,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (book_id) REFERENCES ebook_library(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_scripts_book ON scripts(book_id);

        CREATE TABLE IF NOT EXISTS script_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 1,
            title TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            word_count INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_script_chapters_script ON script_chapters(script_id);
        CREATE INDEX IF NOT EXISTS idx_script_chapters_idx ON script_chapters(script_id, chapter_index);

        CREATE TABLE IF NOT EXISTS script_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 1,
            line_no INTEGER DEFAULT 0,
            role TEXT DEFAULT '',
            instruction TEXT DEFAULT '',
            content TEXT DEFAULT '',
            seed INTEGER DEFAULT 0,
            created_at REAL,
            type TEXT DEFAULT 'narration',
            prev_id INTEGER DEFAULT NULL,
            next_id INTEGER DEFAULT NULL,
            tone TEXT DEFAULT '',
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_script_lines_script ON script_lines(script_id);
        CREATE INDEX IF NOT EXISTS idx_script_lines_chapter ON script_lines(script_id, chapter_index);

        CREATE TABLE IF NOT EXISTS script_characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            line_count INTEGER DEFAULT 0,
            gender TEXT DEFAULT '',
            age TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_script_characters_unique
            ON script_characters(script_id, role);
        CREATE INDEX IF NOT EXISTS idx_script_characters_script
            ON script_characters(script_id);

        CREATE TABLE IF NOT EXISTS script_character_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            agent_id TEXT DEFAULT '',
            speed REAL DEFAULT 1.0,
            seed INTEGER DEFAULT 0,
            tts_capability_id TEXT DEFAULT '',
            cloud_extra_params TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_script_char_config_unique
            ON script_character_configs(script_id, role);

        CREATE TABLE IF NOT EXISTS script_line_audio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id INTEGER NOT NULL,
            content TEXT DEFAULT '',
            role TEXT DEFAULT '',
            tone TEXT DEFAULT '',
            instruction TEXT DEFAULT '',
            agent_id TEXT DEFAULT '',
            tts_capability_id TEXT DEFAULT '',
            seed INTEGER DEFAULT 0,
            audio_path TEXT DEFAULT '',
            audio_volume REAL DEFAULT 1.0,
            audio_pitch INTEGER DEFAULT 0,
            fade_in REAL DEFAULT 0.0,
            fade_out REAL DEFAULT 0.0,
            audio_adjust_enabled INTEGER DEFAULT 0,
            range_start REAL DEFAULT 0.0,
            range_end REAL DEFAULT 0.0,
            created_at REAL,
            FOREIGN KEY (line_id) REFERENCES script_lines(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_audio_history_line ON script_line_audio_history(line_id);
        CREATE INDEX IF NOT EXISTS idx_audio_history_line_time ON script_line_audio_history(line_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS chapter_audio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 1,
            chapter_title TEXT DEFAULT '',
            audio_path TEXT DEFAULT '',
            srt_path TEXT DEFAULT '',
            duration REAL DEFAULT 0.0,
            line_count INTEGER DEFAULT 0,
            generated_count INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chapter_audio_history
            ON chapter_audio_history(script_id, chapter_index);
        CREATE INDEX IF NOT EXISTS idx_chapter_audio_history_time
            ON chapter_audio_history(script_id, chapter_index, created_at DESC);

        CREATE TABLE IF NOT EXISTS ebook_chapter_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 1,
            sentence_index INTEGER DEFAULT 0,
            content TEXT DEFAULT '',
            char_count INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (book_id) REFERENCES ebook_library(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_ebook_sentences_book
            ON ebook_chapter_sentences(book_id, chapter_index);
        CREATE INDEX IF NOT EXISTS idx_ebook_sentences_idx
            ON ebook_chapter_sentences(book_id, chapter_index, sentence_index);

        CREATE TABLE IF NOT EXISTS ebook_sentence_audio_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT '',
            seed INTEGER DEFAULT 0,
            instruction TEXT DEFAULT '',
            speed REAL DEFAULT 1.0,
            audio_path TEXT DEFAULT '',
            duration REAL DEFAULT 0.0,
            file_size INTEGER DEFAULT 0,
            created_at REAL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_audio_cache_unique
            ON ebook_sentence_audio_cache(content_hash, agent_id, seed, instruction, speed);
        CREATE INDEX IF NOT EXISTS idx_audio_cache_hash
            ON ebook_sentence_audio_cache(content_hash);

        CREATE TABLE IF NOT EXISTS capability_test_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capability_type TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            platform_code TEXT NOT NULL,
            model_code TEXT NOT NULL,
            input_data TEXT NOT NULL,
            output_data TEXT DEFAULT '',
            status TEXT DEFAULT 'success',
            error_message TEXT DEFAULT '',
            duration REAL DEFAULT 0.0,
            created_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_cap_test_type
            ON capability_test_history(capability_type);
        CREATE INDEX IF NOT EXISTS idx_cap_test_time
            ON capability_test_history(created_at DESC);

        CREATE TABLE IF NOT EXISTS script_writing_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 0,
            task_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            prompt TEXT DEFAULT '',
            context TEXT DEFAULT '',
            draft TEXT DEFAULT '',
            polished TEXT DEFAULT '',
            review_result TEXT DEFAULT '',
            facts_recorded TEXT DEFAULT '',
            progress INTEGER DEFAULT 0,
            progress_message TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            current_step TEXT DEFAULT '',
            step_result TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_writing_tasks_script
            ON script_writing_tasks(script_id);
        CREATE INDEX IF NOT EXISTS idx_writing_tasks_status
            ON script_writing_tasks(status);

        CREATE TABLE IF NOT EXISTS script_chapter_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 0,
            content TEXT DEFAULT '',
            word_count INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chapter_versions_script
            ON script_chapter_versions(script_id);
        CREATE INDEX IF NOT EXISTS idx_chapter_versions_chapter
            ON script_chapter_versions(script_id, chapter_index);

        CREATE TABLE IF NOT EXISTS script_writing_pipeline_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            chapter_index INTEGER DEFAULT 0,
            task_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            step_result TEXT DEFAULT '',
            success INTEGER DEFAULT 1,
            error_message TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_logs_task
            ON script_writing_pipeline_logs(task_id);
        CREATE INDEX IF NOT EXISTS idx_pipeline_logs_script
            ON script_writing_pipeline_logs(script_id);

        CREATE TABLE IF NOT EXISTS webnovel_project (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            genre_label TEXT DEFAULT '',
            target_words INTEGER DEFAULT 0,
            target_chapters INTEGER DEFAULT 0,
            one_liner TEXT DEFAULT '',
            story_summary TEXT DEFAULT '',
            core_conflict TEXT DEFAULT '',
            target_reader TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            anti_trope_rules TEXT DEFAULT '',
            hard_constraints TEXT DEFAULT '',
            core_selling_points TEXT DEFAULT '',
            opening_hook TEXT DEFAULT '',
            protagonist_name TEXT DEFAULT '',
            protagonist_flaw TEXT DEFAULT '',
            villain_mirror TEXT DEFAULT '',
            protagonist_desire TEXT DEFAULT '',
            protagonist_archetype TEXT DEFAULT '',
            protagonist_structure TEXT DEFAULT '单主角',
            heroine_config TEXT DEFAULT '',
            heroine_names TEXT DEFAULT '',
            heroine_role TEXT DEFAULT '',
            co_protagonists TEXT DEFAULT '',
            co_protagonist_roles TEXT DEFAULT '',
            antagonist_tiers TEXT DEFAULT '',
            antagonist_level TEXT DEFAULT '',
            golden_finger_name TEXT DEFAULT '',
            golden_finger_type TEXT DEFAULT '',
            golden_finger_style TEXT DEFAULT '',
            gf_visibility TEXT DEFAULT '',
            gf_irreversible_cost TEXT DEFAULT '',
            world_scale TEXT DEFAULT '',
            factions TEXT DEFAULT '',
            power_system_type TEXT DEFAULT '',
            social_class TEXT DEFAULT '',
            resource_distribution TEXT DEFAULT '',
            currency_system TEXT DEFAULT '',
            currency_exchange TEXT DEFAULT '',
            sect_hierarchy TEXT DEFAULT '',
            cultivation_chain TEXT DEFAULT '',
            cultivation_subtiers TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_project_script ON webnovel_project(script_id);

        CREATE TABLE IF NOT EXISTS webnovel_init_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            current_step INTEGER DEFAULT 2,
            status TEXT DEFAULT 'active',
            project_data TEXT DEFAULT '{}',
            protagonist_data TEXT DEFAULT '{}',
            relationship_data TEXT DEFAULT '{}',
            golden_finger_data TEXT DEFAULT '{}',
            world_data TEXT DEFAULT '{}',
            constraints_data TEXT DEFAULT '{}',
            ai_generated_data TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_init_script ON webnovel_init_session(script_id);

        CREATE TABLE IF NOT EXISTS webnovel_golden_finger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            genre_fit TEXT DEFAULT '',
            main_role TEXT DEFAULT '',
            visibility TEXT DEFAULT '',
            type TEXT DEFAULT '',
            core_function TEXT DEFAULT '',
            visual_expression TEXT DEFAULT '',
            trigger_condition TEXT DEFAULT '',
            acquisition_event TEXT DEFAULT '',
            cost_limitation TEXT DEFAULT '',
            irreversible_cost TEXT DEFAULT '',
            cooldown_limit TEXT DEFAULT '',
            forbidden_items TEXT DEFAULT '',
            failure_penalty TEXT DEFAULT '',
            counter_method TEXT DEFAULT '',
            anti_trope_alignment TEXT DEFAULT '',
            hard_constraint_binding TEXT DEFAULT '',
            protagonist_flaw_effect TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_gf_project ON webnovel_golden_finger(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_golden_finger_upgrade (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            golden_finger_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            description TEXT DEFAULT '',
            FOREIGN KEY (golden_finger_id) REFERENCES webnovel_golden_finger(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_gf_upgrade ON webnovel_golden_finger_upgrade(golden_finger_id);

        CREATE TABLE IF NOT EXISTS webnovel_golden_finger_payoff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            golden_finger_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT DEFAULT '',
            FOREIGN KEY (golden_finger_id) REFERENCES webnovel_golden_finger(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_gf_payoff ON webnovel_golden_finger_payoff(golden_finger_id);

        CREATE TABLE IF NOT EXISTS webnovel_golden_finger_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            golden_finger_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            chapter_interval INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            FOREIGN KEY (golden_finger_id) REFERENCES webnovel_golden_finger(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_gf_feedback ON webnovel_golden_finger_feedback(golden_finger_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_card (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            character_type TEXT NOT NULL,
            name TEXT DEFAULT '',
            alias TEXT DEFAULT '',
            age INTEGER DEFAULT 0,
            age_stage TEXT DEFAULT '',
            identity TEXT DEFAULT '',
            protagonist_relation TEXT DEFAULT '',
            starting_state TEXT DEFAULT '',
            core_tags TEXT DEFAULT '',
            first_impression TEXT DEFAULT '',
            core_personality TEXT DEFAULT '',
            behavior_bottom_line TEXT DEFAULT '',
            emotion_triggers TEXT DEFAULT '',
            easy_to_anger TEXT DEFAULT '',
            easy_to_soften TEXT DEFAULT '',
            short_term_goal TEXT DEFAULT '',
            medium_term_goal TEXT DEFAULT '',
            long_term_goal TEXT DEFAULT '',
            true_desire TEXT DEFAULT '',
            personality_flaw TEXT DEFAULT '',
            ability_limit TEXT DEFAULT '',
            psychological_shadow TEXT DEFAULT '',
            cost_tolerance TEXT DEFAULT '',
            behavior_pattern TEXT DEFAULT '',
            failure_reaction TEXT DEFAULT '',
            breakthrough_strength TEXT DEFAULT '',
            ooc_warnings TEXT DEFAULT '',
            need_foreshadowing TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_char_project ON webnovel_character_card(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_char_type ON webnovel_character_card(project_id, character_type);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_webnovel_char_unique_name
            ON webnovel_character_card(project_id, name)
            WHERE name != '';

        CREATE TABLE IF NOT EXISTS webnovel_character_relationship (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            target_character_id INTEGER DEFAULT NULL,
            target_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            FOREIGN KEY (character_id) REFERENCES webnovel_character_card(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_char_relation ON webnovel_character_relationship(character_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_growth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            description TEXT DEFAULT '',
            FOREIGN KEY (character_id) REFERENCES webnovel_character_card(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_char_growth ON webnovel_character_growth(character_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_power (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            realm TEXT DEFAULT '',
            layer INTEGER DEFAULT 0,
            bottleneck TEXT DEFAULT '',
            signature_skills TEXT DEFAULT '',
            resources_equipment TEXT DEFAULT '',
            FOREIGN KEY (character_id) REFERENCES webnovel_character_card(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_char_power ON webnovel_character_power(character_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            source TEXT DEFAULT '',
            acquired_chapter INTEGER DEFAULT 0,
            lost_chapter INTEGER DEFAULT 0,
            change_note TEXT DEFAULT '',
            quantity INTEGER DEFAULT 1,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (character_id) REFERENCES webnovel_character_card(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_char_item ON webnovel_character_item(character_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_webnovel_char_item_unique
            ON webnovel_character_item(character_id, item_name);

        CREATE TABLE IF NOT EXISTS webnovel_character_group (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            common_goal TEXT DEFAULT '',
            stage_goal TEXT DEFAULT '',
            decision_maker TEXT DEFAULT '',
            executor TEXT DEFAULT '',
            information_hub TEXT DEFAULT '',
            emotional_pivot TEXT DEFAULT '',
            pov_ratio TEXT DEFAULT '',
            rotation_rules TEXT DEFAULT '',
            anti_overpower_constraints TEXT DEFAULT '',
            value_conflicts TEXT DEFAULT '',
            resource_conflicts TEXT DEFAULT '',
            trust_cracks TEXT DEFAULT '',
            anti_trope_influence TEXT DEFAULT '',
            hard_constraint_cooperation TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_group_project ON webnovel_character_group(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_group_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            character_id INTEGER,
            role TEXT DEFAULT '',
            main_line_contribution TEXT DEFAULT '',
            key_flaw TEXT DEFAULT '',
            key_ability TEXT DEFAULT '',
            FOREIGN KEY (group_id) REFERENCES webnovel_character_group(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_group_member ON webnovel_character_group_member(group_id);

        CREATE TABLE IF NOT EXISTS webnovel_character_group_arc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            description TEXT DEFAULT '',
            FOREIGN KEY (group_id) REFERENCES webnovel_character_group(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_group_arc ON webnovel_character_group_arc(group_id);

        CREATE TABLE IF NOT EXISTS webnovel_villain (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            identity_faction TEXT DEFAULT '',
            appearance_timing TEXT DEFAULT '',
            core_desire TEXT DEFAULT '',
            core_fear TEXT DEFAULT '',
            action_principle TEXT DEFAULT '',
            shared_desire_flaw TEXT DEFAULT '',
            villain_path TEXT DEFAULT '',
            value_conflict_points TEXT DEFAULT '',
            power_level TEXT DEFAULT '',
            key_abilities TEXT DEFAULT '',
            organization_resources TEXT DEFAULT '',
            restricted_rules TEXT DEFAULT '',
            cost_mechanism TEXT DEFAULT '',
            counter_points TEXT DEFAULT '',
            can_be_redeemed INTEGER DEFAULT 0,
            has_higher_villain INTEGER DEFAULT 0,
            upgrade_rhythm TEXT DEFAULT '',
            power_ladder TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_villain_project ON webnovel_villain(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_villain_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            villain_id INTEGER NOT NULL,
            tier TEXT NOT NULL,
            villain_name TEXT DEFAULT '',
            stage TEXT DEFAULT '',
            goal TEXT DEFAULT '',
            protagonist_relation TEXT DEFAULT '',
            FOREIGN KEY (villain_id) REFERENCES webnovel_villain(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_villain_hierarchy ON webnovel_villain_hierarchy(villain_id);

        CREATE TABLE IF NOT EXISTS webnovel_villain_plot_node (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            villain_id INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            chapter INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            FOREIGN KEY (villain_id) REFERENCES webnovel_villain(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_villain_plot ON webnovel_villain_plot_node(villain_id);

        CREATE TABLE IF NOT EXISTS webnovel_power_system (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            core_creed TEXT DEFAULT '',
            cost_rules TEXT DEFAULT '',
            fairness_principle TEXT DEFAULT '',
            system_type TEXT DEFAULT '',
            typical_realm_chain TEXT DEFAULT '',
            small_realm_divisions TEXT DEFAULT '',
            energy_source TEXT DEFAULT '',
            training_methods TEXT DEFAULT '',
            social_control_mechanism TEXT DEFAULT '',
            resource_types TEXT DEFAULT '',
            resource_acquisition TEXT DEFAULT '',
            scarcity_rules TEXT DEFAULT '',
            alternative_paths TEXT DEFAULT '',
            damage_defense_logic TEXT DEFAULT '',
            battle_rhythm TEXT DEFAULT '',
            counter_relations TEXT DEFAULT '',
            escape_mechanism TEXT DEFAULT '',
            forbidden_arts TEXT DEFAULT '',
            high_level_limits TEXT DEFAULT '',
            hard_limits TEXT DEFAULT '',
            system_vulnerabilities TEXT DEFAULT '',
            protagonist_exploitation TEXT DEFAULT '',
            villain_counter TEXT DEFAULT '',
            anti_trope_alignment TEXT DEFAULT '',
            hard_constraint_binding TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_power_project ON webnovel_power_system(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_power_level (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            power_system_id INTEGER NOT NULL,
            level_order INTEGER NOT NULL,
            level_name TEXT DEFAULT '',
            core_abilities TEXT DEFAULT '',
            resource_requirements TEXT DEFAULT '',
            breakthrough_method TEXT DEFAULT '',
            failure_cost TEXT DEFAULT '',
            overlevel_cost TEXT DEFAULT '',
            FOREIGN KEY (power_system_id) REFERENCES webnovel_power_system(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_power_level ON webnovel_power_level(power_system_id);

        CREATE TABLE IF NOT EXISTS webnovel_power_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            power_system_id INTEGER NOT NULL,
            realm_change_chapter INTEGER DEFAULT 0,
            power_gap_display TEXT DEFAULT '',
            FOREIGN KEY (power_system_id) REFERENCES webnovel_power_system(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_power_feedback ON webnovel_power_feedback(power_system_id);

        CREATE TABLE IF NOT EXISTS webnovel_worldview (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            world_summary TEXT DEFAULT '',
            main_genre TEXT DEFAULT '',
            sub_genre TEXT DEFAULT '',
            fusion_mechanism TEXT DEFAULT '',
            continent_count INTEGER DEFAULT 0,
            core_regions TEXT DEFAULT '',
            edge_regions TEXT DEFAULT '',
            social_hierarchy TEXT DEFAULT '',
            resource_distribution TEXT DEFAULT '',
            belief_ideology TEXT DEFAULT '',
            resource_scarcity TEXT DEFAULT '',
            political_rules TEXT DEFAULT '',
            social_common_sense TEXT DEFAULT '',
            hard_constraints TEXT DEFAULT '',
            energy_cycle TEXT DEFAULT '',
            technology_basis TEXT DEFAULT '',
            fairness_cost_rules TEXT DEFAULT '',
            currency_system TEXT DEFAULT '',
            exchange_rules TEXT DEFAULT '',
            main_currency_form TEXT DEFAULT '',
            trading_scenes TEXT DEFAULT '',
            important_locations TEXT DEFAULT '',
            key_resource_points TEXT DEFAULT '',
            daily_currency TEXT DEFAULT '',
            transportation_communication TEXT DEFAULT '',
            education_career TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_worldview_project ON webnovel_worldview(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_worldview_faction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worldview_id INTEGER NOT NULL,
            faction_name TEXT DEFAULT '',
            tier TEXT DEFAULT '',
            relation TEXT DEFAULT '',
            hierarchy TEXT DEFAULT '',
            FOREIGN KEY (worldview_id) REFERENCES webnovel_worldview(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_worldview_faction ON webnovel_worldview_faction(worldview_id);

        CREATE TABLE IF NOT EXISTS webnovel_worldview_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worldview_id INTEGER NOT NULL,
            era TEXT DEFAULT '',
            event TEXT DEFAULT '',
            FOREIGN KEY (worldview_id) REFERENCES webnovel_worldview(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_worldview_history ON webnovel_worldview_history(worldview_id);

        CREATE TABLE IF NOT EXISTS webnovel_volume_outline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            volume_number INTEGER NOT NULL,
            volume_name TEXT DEFAULT '',
            chapter_start INTEGER DEFAULT 0,
            chapter_end INTEGER DEFAULT 0,
            core_conflict TEXT DEFAULT '',
            volume_climax TEXT DEFAULT '',
            promise_description TEXT DEFAULT '',
            promise_types TEXT DEFAULT '',
            catalyst_event TEXT DEFAULT '',
            irreversible_change TEXT DEFAULT '',
            protagonist_goal TEXT DEFAULT '',
            mid_reversal TEXT DEFAULT '',
            reversal_insight TEXT DEFAULT '',
            lowest_point_event TEXT DEFAULT '',
            lowest_point_cost TEXT DEFAULT '',
            protagonist_choice TEXT DEFAULT '',
            payoff_items TEXT DEFAULT '',
            new_hook TEXT DEFAULT '',
            unresolved_issues TEXT DEFAULT '',
            core_conflict_anchor TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_volume_project ON webnovel_volume_outline(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_foreshadow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            volume_outline_id INTEGER NOT NULL,
            content TEXT DEFAULT '',
            buried_chapter INTEGER DEFAULT 0,
            payoff_chapter INTEGER DEFAULT 0,
            level TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE,
            FOREIGN KEY (volume_outline_id) REFERENCES webnovel_volume_outline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_foreshadow_project ON webnovel_foreshadow(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_foreshadow_volume ON webnovel_foreshadow(volume_outline_id);

        CREATE TABLE IF NOT EXISTS webnovel_volume_crisis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_outline_id INTEGER NOT NULL,
            crisis_order INTEGER NOT NULL,
            crisis_event TEXT DEFAULT '',
            cost_risk_upgrade TEXT DEFAULT '',
            result_change TEXT DEFAULT '',
            FOREIGN KEY (volume_outline_id) REFERENCES webnovel_volume_outline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_volume_crisis ON webnovel_volume_crisis(volume_outline_id);

        CREATE TABLE IF NOT EXISTS webnovel_chapter_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_outline_id INTEGER NOT NULL,
            chapter_index INTEGER NOT NULL,
            chapter_title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            key_events TEXT DEFAULT '',
            expected_cool_points TEXT DEFAULT '',
            foreshadowing TEXT DEFAULT '',
            chapter_hook TEXT DEFAULT '',
            chapter_goal TEXT DEFAULT '',
            resistance TEXT DEFAULT '',
            cost TEXT DEFAULT '',
            time_anchor TEXT DEFAULT '',
            chapter_duration TEXT DEFAULT '',
            interval_from_prev TEXT DEFAULT '',
            countdown_status TEXT DEFAULT '',
            strand TEXT DEFAULT '',
            villain_tier TEXT DEFAULT '',
            perspective TEXT DEFAULT '',
            key_entities TEXT DEFAULT '',
            chapter_change TEXT DEFAULT '',
            unresolved_questions TEXT DEFAULT '',
            cbn TEXT DEFAULT '',
            cpns TEXT DEFAULT '',
            cen TEXT DEFAULT '',
            must_cover_nodes TEXT DEFAULT '',
            forbidden_zones TEXT DEFAULT '',
            FOREIGN KEY (volume_outline_id) REFERENCES webnovel_volume_outline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_chapter_plan_volume ON webnovel_chapter_plan(volume_outline_id);

        CREATE TABLE IF NOT EXISTS webnovel_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            volume_number INTEGER NOT NULL,
            time_base TEXT DEFAULT '',
            time_span TEXT DEFAULT '',
            countdown_events TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_timeline_project ON webnovel_timeline(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_timeline_volume ON webnovel_timeline(project_id, volume_number);

        CREATE TABLE IF NOT EXISTS webnovel_timeline_chapter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timeline_id INTEGER NOT NULL,
            chapter_number INTEGER NOT NULL,
            time_anchor TEXT DEFAULT '',
            chapter_duration TEXT DEFAULT '',
            interval_from_prev TEXT DEFAULT '',
            countdown_status TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (timeline_id) REFERENCES webnovel_timeline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_timeline_chapter ON webnovel_timeline_chapter(timeline_id);

        CREATE TABLE IF NOT EXISTS webnovel_timeline_countdown (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timeline_id INTEGER NOT NULL,
            event_name TEXT DEFAULT '',
            start_countdown TEXT DEFAULT '',
            current_status TEXT DEFAULT '',
            trigger_chapter INTEGER DEFAULT 0,
            result TEXT DEFAULT '',
            FOREIGN KEY (timeline_id) REFERENCES webnovel_timeline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_timeline_countdown ON webnovel_timeline_countdown(timeline_id);

        CREATE TABLE IF NOT EXISTS webnovel_genre_fusion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            main_genre TEXT DEFAULT '',
            sub_genre TEXT DEFAULT '',
            proportion TEXT DEFAULT '',
            shared_core_conflict TEXT DEFAULT '',
            shared_payoff_goal TEXT DEFAULT '',
            reader_promise TEXT DEFAULT '',
            rule_compatibility TEXT DEFAULT '',
            conflict_points TEXT DEFAULT '',
            sub_genre_trigger_condition TEXT DEFAULT '',
            non_mixable_rules TEXT DEFAULT '',
            main_genre_responsibilities TEXT DEFAULT '',
            sub_genre_responsibilities TEXT DEFAULT '',
            rhythm_arrangement TEXT DEFAULT '',
            style_split_points TEXT DEFAULT '',
            setting_conflict_points TEXT DEFAULT '',
            reader_expectation_deviation TEXT DEFAULT '',
            avoidance_methods TEXT DEFAULT '',
            anti_trope_rules TEXT DEFAULT '',
            hard_constraints TEXT DEFAULT '',
            protagonist_flaw_amplification TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_genre_fusion ON webnovel_genre_fusion(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            current_chapter INTEGER DEFAULT 0,
            total_words INTEGER DEFAULT 0,
            volumes_completed TEXT DEFAULT '',
            current_volume INTEGER DEFAULT 1,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_state_project ON webnovel_state(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_plot_thread (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            thread_type TEXT DEFAULT '',
            content TEXT DEFAULT '',
            status TEXT DEFAULT '',
            chapter INTEGER DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_plot_thread ON webnovel_plot_thread(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_chapter_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_number INTEGER NOT NULL,
            hook_type TEXT DEFAULT '',
            hook_content TEXT DEFAULT '',
            hook_strength TEXT DEFAULT '',
            opening_pattern TEXT DEFAULT '',
            hook_pattern TEXT DEFAULT '',
            emotion_rhythm TEXT DEFAULT '',
            info_density TEXT DEFAULT '',
            ending_time TEXT DEFAULT '',
            ending_location TEXT DEFAULT '',
            ending_emotion TEXT DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_chapter_meta ON webnovel_chapter_meta(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_review_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_number INTEGER DEFAULT 0,
            review_type TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            feedback TEXT DEFAULT '',
            suggestions TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_review_project ON webnovel_review_record(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_review_chapter ON webnovel_review_record(project_id, chapter_number);

        CREATE TABLE IF NOT EXISTS webnovel_csv_genre_tone (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            genre_flow TEXT DEFAULT '',
            canonical_genre TEXT DEFAULT '',
            genre_alias TEXT DEFAULT '',
            core_tone TEXT DEFAULT '',
            pacing_strategy TEXT DEFAULT '',
            pitfalls TEXT DEFAULT '',
            recommended_basic_tables TEXT DEFAULT '',
            recommended_dynamic_tables TEXT DEFAULT '',
            default_query TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_genre_code ON webnovel_csv_genre_tone(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_genre_keywords ON webnovel_csv_genre_tone(keywords);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_genre_applicable ON webnovel_csv_genre_tone(applicable_genre);

        CREATE TABLE IF NOT EXISTS webnovel_csv_golden_finger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            setting_type TEXT DEFAULT '',
            value_control_boundary TEXT DEFAULT '',
            plot_interaction TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_gf_code ON webnovel_csv_golden_finger(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_gf_keywords ON webnovel_csv_golden_finger(keywords);

        CREATE TABLE IF NOT EXISTS webnovel_csv_verdict_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            style_priority TEXT DEFAULT '',
            payoff_priority TEXT DEFAULT '',
            pacing_strategy TEXT DEFAULT '',
            pitfalls_weight TEXT DEFAULT '',
            conflict_verdict TEXT DEFAULT '',
            contract_injection TEXT DEFAULT '',
            anti_pattern TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_verdict_code ON webnovel_csv_verdict_rules(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_verdict_genre ON webnovel_csv_verdict_rules(genre);

        CREATE TABLE IF NOT EXISTS webnovel_csv_pacing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            pacing_type TEXT DEFAULT '',
            emotion_technique TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_pacing_code ON webnovel_csv_pacing(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_pacing_type ON webnovel_csv_pacing(pacing_type);

        CREATE TABLE IF NOT EXISTS webnovel_csv_plot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            plot_name TEXT DEFAULT '',
            setup TEXT DEFAULT '',
            core_payoff TEXT DEFAULT '',
            twist_design TEXT DEFAULT '',
            anti_cliche_variant TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_plot_code ON webnovel_csv_plot(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_plot_name ON webnovel_csv_plot(plot_name);

        CREATE TABLE IF NOT EXISTS webnovel_csv_scene (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            scene_type TEXT DEFAULT '',
            mode_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            example TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_scene_code ON webnovel_csv_scene(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_scene_type ON webnovel_csv_scene(scene_type);

        CREATE TABLE IF NOT EXISTS webnovel_csv_naming (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            naming_object TEXT DEFAULT '',
            rules TEXT DEFAULT '',
            positive_example TEXT DEFAULT '',
            negative_example TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_naming_code ON webnovel_csv_naming(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_naming_object ON webnovel_csv_naming(naming_object);

        CREATE TABLE IF NOT EXISTS webnovel_csv_writing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            technique_type TEXT DEFAULT '',
            technique_name TEXT DEFAULT '',
            applicable_scene TEXT DEFAULT '',
            pitfalls TEXT DEFAULT '',
            positive_example TEXT DEFAULT '',
            negative_example TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_writing_code ON webnovel_csv_writing(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_writing_type ON webnovel_csv_writing(technique_type);

        CREATE TABLE IF NOT EXISTS webnovel_csv_pack (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pack_code TEXT NOT NULL,
            pack_name TEXT NOT NULL,
            category TEXT DEFAULT '',
            category_group TEXT DEFAULT '',
            rules TEXT DEFAULT '',
            character_conflict TEXT DEFAULT '',
            hooks TEXT DEFAULT '',
            cool_points TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_pack_code ON webnovel_csv_pack(pack_code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_pack_category ON webnovel_csv_pack(category);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_pack_group ON webnovel_csv_pack(category_group);

        CREATE TABLE IF NOT EXISTS webnovel_csv_character (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            applicable_skill TEXT DEFAULT '',
            category TEXT DEFAULT '',
            level TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genre TEXT DEFAULT '',
            llm_instruction TEXT DEFAULT '',
            core_summary TEXT DEFAULT '',
            detailed_expand TEXT DEFAULT '',
            character_type TEXT DEFAULT '',
            core_motivation TEXT DEFAULT '',
            behavior_logic TEXT DEFAULT '',
            interaction_pattern TEXT DEFAULT '',
            pitfalls TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_character_code ON webnovel_csv_character(code);
        CREATE INDEX IF NOT EXISTS idx_webnovel_csv_character_type ON webnovel_csv_character(character_type);

        CREATE TABLE IF NOT EXISTS webnovel_idea_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            selected_idea TEXT DEFAULT '{}',
            constraints_inherited TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_idea_bank_project ON webnovel_idea_bank(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_chapter_plot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_index INTEGER NOT NULL,
            plot_order INTEGER NOT NULL DEFAULT 0,
            scene TEXT DEFAULT '',
            description TEXT DEFAULT '',
            characters TEXT DEFAULT '',
            emotion TEXT DEFAULT '',
            conflict TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_chapter_plot_project ON webnovel_chapter_plot(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_chapter_plot_chapter ON webnovel_chapter_plot(project_id, chapter_index);

        CREATE TABLE IF NOT EXISTS webnovel_open_loops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            content TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            tier TEXT DEFAULT '',
            planted_chapter INTEGER DEFAULT 0,
            target_chapter INTEGER DEFAULT 0,
            resolved_chapter INTEGER DEFAULT 0,
            urgency REAL DEFAULT 0.0,
            evidence TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_open_loops_project ON webnovel_open_loops(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_open_loops_status ON webnovel_open_loops(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_webnovel_open_loops_tier ON webnovel_open_loops(project_id, tier);

        CREATE TABLE IF NOT EXISTS webnovel_cool_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_number INTEGER DEFAULT 0,
            content TEXT DEFAULT '',
            cool_point_type TEXT DEFAULT '',
            execution_mode TEXT DEFAULT '',
            structure_stage TEXT DEFAULT '',
            pressure_level INTEGER DEFAULT 0,
            release_level INTEGER DEFAULT 0,
            timing_position TEXT DEFAULT '',
            reader_emotion TEXT DEFAULT '',
            impact_score INTEGER DEFAULT 0,
            evidence TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_cool_points_project ON webnovel_cool_points(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_cool_points_chapter ON webnovel_cool_points(project_id, chapter_number);
        CREATE INDEX IF NOT EXISTS idx_webnovel_cool_points_type ON webnovel_cool_points(project_id, cool_point_type);

        CREATE TABLE IF NOT EXISTS webnovel_master_setting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            content_json TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_webnovel_master_setting_project ON webnovel_master_setting(project_id);

        CREATE TABLE IF NOT EXISTS webnovel_anti_pattern (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            pattern TEXT DEFAULT '',
            severity TEXT DEFAULT 'medium',
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_anti_pattern_project ON webnovel_anti_pattern(project_id);
        """
    )

    # 迁移：为已存在的 scripts 表添加 progress 字段（如果不存在）
    try:
        cursor = conn.execute("PRAGMA table_info(scripts)")
        columns = [row[1] for row in cursor.fetchall()]
        if "progress" not in columns:
            conn.execute("ALTER TABLE scripts ADD COLUMN progress INTEGER DEFAULT 0")
            conn.commit()  # WAL 模式下必须显式提交，否则变更可能不可见
    except Exception:
        pass  # 表不存在时忽略
