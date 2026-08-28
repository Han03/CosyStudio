function showWorldModal() {
    document.getElementById('worldModal').style.display = 'flex';
    loadWebnovelWorldview();
}

function closeWorldModal() {
    document.getElementById('worldModal').style.display = 'none';
}

function switchWorldTab(tab) {
    state.currentWorldTab = tab;
    document.querySelectorAll('.world-tab-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    loadWebnovelWorldview();
}

async function loadWebnovelWorldview() {
    if (!state.scriptId) {
        renderWebnovelWorldview(null);
        return;
    }
    try {
        if (state.currentWorldTab === 'worldstate') {
            const data = await apiRequest(`/api/books/scripts/webnovel-world-state?script_id=${state.scriptId}`, { silent: true });
            renderWorldState(data);
        } else if (state.currentWorldTab === 'characters') {
            const data = await apiRequest(`/api/books/scripts/webnovel-character-cards?script_id=${state.scriptId}`, { silent: true });
            renderCharacterCards(data);
        } else if (state.currentWorldTab === 'goldenfinger') {
            const data = await apiRequest(`/api/books/scripts/webnovel-golden-finger?script_id=${state.scriptId}`, { silent: true });
            renderGoldenFinger(data);
        } else if (state.currentWorldTab === 'timeline') {
            const data = await apiRequest(`/api/books/scripts/webnovel-timeline?script_id=${state.scriptId}`, { silent: true });
            renderTimeline(data);
        } else if (state.currentWorldTab === 'villain') {
            const data = await apiRequest(`/api/books/scripts/webnovel-villain?script_id=${state.scriptId}`, { silent: true });
            renderVillain(data);
        } else if (state.currentWorldTab === 'powersystem') {
            const data = await apiRequest(`/api/books/scripts/webnovel-power-system?script_id=${state.scriptId}`, { silent: true });
            renderPowerSystem(data);
        } else if (state.currentWorldTab === 'coolpoints') {
            const data = await apiRequest(`/api/books/scripts/webnovel-cool-points?script_id=${state.scriptId}`, { silent: true });
            renderCoolPoints(data);
        } else if (state.currentWorldTab === 'openloops') {
            const data = await apiRequest(`/api/books/scripts/webnovel-open-loops?script_id=${state.scriptId}`, { silent: true });
            renderOpenLoops(data);
        } else {
            const data = await apiRequest(`/api/books/scripts/webnovel-worldview?script_id=${state.scriptId}`, { silent: true });
            renderWebnovelWorldview(data);
        }
    } catch (e) {
        console.error('加载网文世界观失败:', e);
        if (state.currentWorldTab === 'worldstate') renderWorldState(null);
        else if (state.currentWorldTab === 'characters') renderCharacterCards(null);
        else if (state.currentWorldTab === 'goldenfinger') renderGoldenFinger(null);
        else if (state.currentWorldTab === 'timeline') renderTimeline(null);
        else if (state.currentWorldTab === 'villain') renderVillain(null);
        else if (state.currentWorldTab === 'powersystem') renderPowerSystem(null);
        else if (state.currentWorldTab === 'coolpoints') renderCoolPoints(null);
        else if (state.currentWorldTab === 'openloops') renderOpenLoops(null);
        else renderWebnovelWorldview(null);
    }
}

function renderWebnovelWorldview(data) {
    const container = document.getElementById('worldContent');
    
    if (!data || !data.success || !data.project) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-globe"></i>
                <p>暂无网文世界观数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }
    
    const project = data.project;
    const worldview = data.worldview || {};
    const powerSystem = data.power_system || {};
    
    let html = `
        <div class="webnovel-worldview">
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-info-circle"></i> 项目基本信息
                </div>
                <div class="webnovel-info-grid">
                    <div class="webnovel-info-item">
                        <span class="webnovel-info-label">书名</span>
                        <span class="webnovel-info-value">${project.title || '-'}</span>
                    </div>
                    <div class="webnovel-info-item">
                        <span class="webnovel-info-label">题材</span>
                        <span class="webnovel-info-value">${project.genre_label || project.genre || '-'}</span>
                    </div>
                    <div class="webnovel-info-item">
                        <span class="webnovel-info-label">目标字数</span>
                        <span class="webnovel-info-value">${project.target_words ? project.target_words.toLocaleString() + '字' : '-'}</span>
                    </div>
                    <div class="webnovel-info-item">
                        <span class="webnovel-info-label">目标章节</span>
                        <span class="webnovel-info-value">${project.target_chapters ? project.target_chapters + '章' : '-'}</span>
                    </div>
                </div>
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-star"></i> 核心卖点
                </div>
                <div class="webnovel-text-content">${project.core_selling_points || '<span style="color:var(--neu-text-muted)">暂无</span>'}</div>
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-quote-right"></i> 一句话简介
                </div>
                <div class="webnovel-text-content">${project.one_liner || '<span style="color:var(--neu-text-muted)">暂无</span>'}</div>
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-book"></i> 故事梗概
                </div>
                <div class="webnovel-text-content">${project.story_summary || '<span style="color:var(--neu-text-muted)">暂无</span>'}</div>
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-globe"></i> 世界观设定
                </div>
                ${worldview.world_scale ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">世界规模：</span><span>${worldview.world_scale}</span></div>` : ''}
                ${worldview.factions ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">势力分布：</span><span>${worldview.factions.replace(/\\n/g, '<br>')}</span></div>` : ''}
                ${worldview.social_class ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">社会阶层：</span><span>${worldview.social_class.replace(/\\n/g, '<br>')}</span></div>` : ''}
                ${worldview.resource_distribution ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">资源分布：</span><span>${worldview.resource_distribution.replace(/\\n/g, '<br>')}</span></div>` : ''}
                ${worldview.currency_system ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">货币体系：</span><span>${worldview.currency_system.replace(/\\n/g, '<br>')}</span></div>` : ''}
                ${worldview.world_summary ? `<div class="webnovel-detail-item" style="margin-top:8px;"><span class="webnovel-detail-label">世界简介：</span><span>${worldview.world_summary.replace(/\\n/g, '<br>')}</span></div>` : ''}
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-zap"></i> 力量体系
                </div>
                ${powerSystem.power_system_type ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">体系类型：</span><span>${powerSystem.power_system_type}</span></div>` : ''}
                ${powerSystem.cultivation_chain ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">修炼等级：</span><span>${powerSystem.cultivation_chain}</span></div>` : ''}
                ${powerSystem.cultivation_subtiers ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">细分境界：</span><span>${powerSystem.cultivation_subtiers}</span></div>` : ''}
                ${powerSystem.sect_hierarchy ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">宗门层级：</span><span>${powerSystem.sect_hierarchy}</span></div>` : ''}
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-hand-sparkles"></i> 金手指
                </div>
                ${project.golden_finger_name ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">名称：</span><span>${project.golden_finger_name}</span></div>` : ''}
                ${project.golden_finger_type ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">类型：</span><span>${project.golden_finger_type}</span></div>` : ''}
                ${project.golden_finger_style ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">风格：</span><span>${project.golden_finger_style}</span></div>` : ''}
                ${project.gf_visibility ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">可见性：</span><span>${project.gf_visibility}</span></div>` : ''}
                ${project.gf_irreversible_cost ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">不可逆代价：</span><span>${project.gf_irreversible_cost}</span></div>` : ''}
            </div>
            
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-user"></i> 主角设定
                </div>
                ${project.protagonist_name ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">姓名：</span><span>${project.protagonist_name}</span></div>` : ''}
                ${project.protagonist_archetype ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">原型：</span><span>${project.protagonist_archetype}</span></div>` : ''}
                ${project.protagonist_desire ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">核心欲望：</span><span>${project.protagonist_desire}</span></div>` : ''}
                ${project.protagonist_flaw ? `<div class="webnovel-detail-item"><span class="webnovel-detail-label">核心缺陷：</span><span>${project.protagonist_flaw}</span></div>` : ''}
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

function renderWorldState(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-mountain"></i>
                <p>暂无世界状态数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const wv = data.worldview;
    const factions = data.factions || [];
    const historyEvents = data.history_events || [];

    if (!wv) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-mountain"></i>
                <p>暂无世界观数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    // ── 辅助函数：生成信息格子项 ──
    const gridItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-info-item">
            <span class="webnovel-info-label">${label}</span>
            <span class="webnovel-info-value">${value}</span>
        </div>`;
    };

    // ── 辅助函数：生成详情项 ──
    const detailItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-detail-item"><span class="webnovel-detail-label">${label}</span><span>${value}</span></div>`;
    };

    let html = '<div class="webnovel-worldview">';

    // ══════════ 世界概览 ══════════
    html += `
        <div class="webnovel-section">
            <div class="webnovel-section-title">
                <i class="fas fa-globe-americas"></i> 世界概览
            </div>
            ${wv.world_summary ? `<div class="webnovel-text-content" style="margin-bottom:10px;">${wv.world_summary}</div>` : ''}
            <div class="webnovel-info-grid">
                ${gridItem('主题材', wv.main_genre)}
                ${gridItem('副题材', wv.sub_genre)}
                ${gridItem('融合机制', wv.fusion_mechanism)}
                ${gridItem('大陆/位面数量', wv.continent_count)}
            </div>
        </div>
    `;

    // ══════════ 世界结构 ══════════
    const structureFields = [
        detailItem('核心区域：', wv.core_regions),
        detailItem('边缘区域：', wv.edge_regions),
        detailItem('重要地点：', wv.important_locations),
        detailItem('关键资源点：', wv.key_resource_points),
    ].filter(Boolean).join('');
    if (structureFields) {
        html += `
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-map-marked-alt"></i> 世界结构
                </div>
                ${structureFields}
            </div>
        `;
    }

    // ══════════ 社会与规则 ══════════
    const socialFields = [
        detailItem('社会阶层：', wv.social_hierarchy),
        detailItem('资源分配：', wv.resource_distribution),
        detailItem('信仰意识形态：', wv.belief_ideology),
        detailItem('资源稀缺性：', wv.resource_scarcity),
        detailItem('政治规则：', wv.political_rules),
        detailItem('社会常识/禁忌：', wv.social_common_sense),
        detailItem('硬约束：', wv.hard_constraints),
    ].filter(Boolean).join('');
    if (socialFields) {
        html += `
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-balance-scale"></i> 社会与规则
                </div>
                ${socialFields}
            </div>
        `;
    }

    // ══════════ 世界运转机制 ══════════
    const mechFields = [
        detailItem('能量循环：', wv.energy_cycle),
        detailItem('技术基础：', wv.technology_basis),
        detailItem('公平与代价规则：', wv.fairness_cost_rules),
        detailItem('货币体系：', wv.currency_system),
        detailItem('交通通讯：', wv.transportation_communication),
    ].filter(Boolean).join('');
    if (mechFields) {
        html += `
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-cogs"></i> 世界运转
                </div>
                ${mechFields}
            </div>
        `;
    }

    // ══════════ 势力格局 ══════════
    if (factions.length > 0) {
        const factionCards = factions.map(f => {
            const tierClass = {'顶级': 'ws-tier-top', '一流': 'ws-tier-high', '二流': 'ws-tier-mid', '新兴': 'ws-tier-new'}[f.tier] || 'ws-tier-mid';
            return `
                <div class="ws-faction-card">
                    <div class="ws-faction-header">
                        <span class="ws-faction-name">${f.faction_name || '未命名'}</span>
                        ${f.tier ? `<span class="ws-faction-tier ${tierClass}">${f.tier}</span>` : ''}
                    </div>
                    ${f.relation ? `<div class="ws-faction-field"><span class="ws-faction-label">关系：</span>${f.relation}</div>` : ''}
                    ${f.hierarchy ? `<div class="ws-faction-field"><span class="ws-faction-label">组织：</span>${f.hierarchy}</div>` : ''}
                </div>
            `;
        }).join('');

        html += `
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-chess-rook"></i> 势力格局 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${factions.length}个)</span>
                </div>
                <div class="ws-faction-grid">
                    ${factionCards}
                </div>
            </div>
        `;
    }

    // ══════════ 历史年表 ══════════
    if (historyEvents.length > 0) {
        const timelineItems = historyEvents.map((e, idx) => {
            const isLast = idx === historyEvents.length - 1;
            return `
                <div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                    <div class="ws-timeline-dot"></div>
                    <div class="ws-timeline-content">
                        ${e.era ? `<div class="ws-timeline-era">${e.era}</div>` : ''}
                        <div class="ws-timeline-event">${e.event || ''}</div>
                    </div>
                </div>
            `;
        }).join('');

        html += `
            <div class="webnovel-section">
                <div class="webnovel-section-title">
                    <i class="fas fa-hourglass-half"></i> 历史年表 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${historyEvents.length}个事件)</span>
                </div>
                <div class="ws-timeline">
                    ${timelineItems}
                </div>
            </div>
        `;
    }

    // 无任何子数据时的提示
    if (factions.length === 0 && historyEvents.length === 0) {
        html += `
            <div class="webnovel-section" style="text-align:center; color:var(--neu-text-muted);">
                <i class="fas fa-info-circle" style="margin-right:4px;"></i>
                势力格局和历史年表数据尚未生成，请重新执行深度初始化
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
}

// ══════════ 角色卡选项卡渲染 ══════════

const CC_TYPE_LABELS = {
    protagonist: '主角', heroine: '女主', villain: '反派',
    supporting: '配角', mentor: '导师', comic_relief: '搞笑担当',
    love_interest: '恋爱对象', rival: '对手', sidekick: '跟班'
};

function renderCharacterCards(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || (!data.characters?.length && !data.groups?.length)) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-users"></i>
                <p>暂无角色卡数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const characters = data.characters || [];
    const groups = data.groups || [];

    // 辅助函数
    const gridItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-info-item">
            <span class="webnovel-info-label">${label}</span>
            <span class="webnovel-info-value">${value}</span>
        </div>`;
    };
    const detailItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-detail-item"><span class="webnovel-detail-label">${label}</span><span>${value}</span></div>`;
    };
    const sectionTitle = (icon, text, count) => {
        const suffix = count != null ? ` <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${count})</span>` : '';
        return `<div class="webnovel-section-title"><i class="fas ${icon}"></i> ${text}${suffix}</div>`;
    };

    // 按 character_type 分组
    const grouped = {};
    characters.forEach(ch => {
        const type = ch.card.character_type || 'other';
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(ch);
    });
    // 排序：主角 > 女主 > 反派 > 其他
    const typeOrder = ['protagonist', 'heroine', 'villain', 'mentor', 'supporting', 'rival', 'love_interest', 'sidekick', 'comic_relief'];
    const sortedTypes = Object.keys(grouped).sort((a, b) => {
        const ia = typeOrder.indexOf(a); const ib = typeOrder.indexOf(b);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    let html = '<div class="webnovel-worldview">';

    // ── 角色卡片列表 ──
    sortedTypes.forEach(type => {
        const chars = grouped[type];
        const typeLabel = CC_TYPE_LABELS[type] || type;
        html += `<div class="webnovel-section">`;
        html += sectionTitle('fa-user', typeLabel + '角色', chars.length);

        chars.forEach(ch => {
            const c = ch.card;
            const relationships = ch.relationships || [];
            const growths = ch.growths || [];
            const power = ch.power;

            html += `<div class="cc-character-card">`;

            // 头部：名称 + 徽章 + 年龄/身份
            html += `<div class="cc-character-header">`;
            html += `<span class="cc-character-name">${c.name || '未命名'}</span>`;
            html += `<span class="cc-type-badge cc-type-${type}">${typeLabel}</span>`;
            if (c.age) html += `<span class="cc-character-age">${c.age}岁</span>`;
            html += `</div>`;

            if (c.identity) {
                html += `<div class="cc-character-identity">${c.identity}</div>`;
            }

            // 信息格：核心标签、初印象、核心性格、行为底线
            const infoGrid = [
                gridItem('核心标签', c.core_tags),
                gridItem('初印象', c.first_impression),
                gridItem('核心性格', c.core_personality),
                gridItem('行为底线', c.behavior_bottom_line),
                gridItem('起始状态', c.starting_state),
                gridItem('情绪触发', c.emotion_triggers),
            ].filter(Boolean).join('');
            if (infoGrid) {
                html += `<div class="cc-info-grid webnovel-info-grid">${infoGrid}</div>`;
            }

            // 目标区
            const goals = [
                detailItem('短期目标：', c.short_term_goal),
                detailItem('中期目标：', c.medium_term_goal),
                detailItem('长期目标：', c.long_term_goal),
                detailItem('真实欲望：', c.true_desire),
            ].filter(Boolean).join('');
            if (goals) {
                html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-bullseye"></i> 目标与欲望</div>${goals}</div>`;
            }

            // 深度区
            const depth = [
                detailItem('性格缺陷：', c.personality_flaw),
                detailItem('能力上限：', c.ability_limit),
                detailItem('心理阴影：', c.psychological_shadow),
                detailItem('行为模式：', c.behavior_pattern),
                detailItem('易怒点：', c.easy_to_anger),
                detailItem('易软化点：', c.easy_to_soften),
                detailItem('代价承受：', c.cost_tolerance),
                detailItem('失败反应：', c.failure_reaction),
                detailItem('突破优势：', c.breakthrough_strength),
                detailItem('OOC警告：', c.ooc_warnings),
                detailItem('需埋伏笔：', c.need_foreshadowing),
            ].filter(Boolean).join('');
            if (depth) {
                html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-brain"></i> 深度设定</div>${depth}</div>`;
            }

            // 人际关系
            if (relationships.length > 0) {
                const relItems = relationships.map(r => {
                    const target = r.target_name || (r.target_character_id ? `角色#${r.target_character_id}` : '未知');
                    return `<div class="cc-relation-item">
                        <span class="cc-relation-type">${r.relation_type}</span>
                        <span class="cc-relation-target">→ ${target}</span>
                        ${r.description ? `<div class="cc-relation-desc">${r.description}</div>` : ''}
                    </div>`;
                }).join('');
                html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-link"></i> 人际关系 (${relationships.length})</div>${relItems}</div>`;
            }

            // 成长轨迹
            if (growths.length > 0) {
                const timelineItems = growths.map((g, idx) => {
                    const isLast = idx === growths.length - 1;
                    return `<div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                        <div class="ws-timeline-dot"></div>
                        <div class="ws-timeline-content">
                            ${g.stage ? `<div class="ws-timeline-era">${g.stage}</div>` : ''}
                            <div class="ws-timeline-event">${g.description || ''}</div>
                        </div>
                    </div>`;
                }).join('');
                html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-chart-line"></i> 成长轨迹 (${growths.length})</div><div class="ws-timeline">${timelineItems}</div></div>`;
            }

            // 战力信息
            if (power) {
                const powerItems = [
                    detailItem('境界：', power.realm),
                    detailItem('层级：', power.layer),
                    detailItem('瓶颈：', power.bottleneck),
                    detailItem('招牌技能：', power.signature_skills),
                    detailItem('资源装备：', power.resources_equipment),
                ].filter(Boolean).join('');
                if (powerItems) {
                    html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-fist-raised"></i> 战力信息</div>${powerItems}</div>`;
                }
            }

            html += `</div>`; // cc-character-card end
        });

        html += `</div>`; // webnovel-section end
    });

    // ── 角色组信息 ──
    groups.forEach(g => {
        const group = g.group;
        const members = g.members || [];
        const arcs = g.arcs || [];

        html += `<div class="webnovel-section">`;
        html += sectionTitle('fa-users', '角色组');

        // 团队基本信息
        const groupFields = [
            detailItem('共同目标：', group.common_goal),
            detailItem('阶段目标：', group.stage_goal),
            detailItem('决策者：', group.decision_maker),
            detailItem('执行者：', group.executor),
            detailItem('信息枢纽：', group.information_hub),
            detailItem('情感支点：', group.emotional_pivot),
            detailItem('视角占比：', group.pov_ratio),
            detailItem('轮换规则：', group.rotation_rules),
            detailItem('反压服约束：', group.anti_overpower_constraints),
            detailItem('价值冲突：', group.value_conflicts),
            detailItem('资源冲突：', group.resource_conflicts),
            detailItem('信任裂痕：', group.trust_cracks),
            detailItem('反套路影响：', group.anti_trope_influence),
            detailItem('硬约束协作：', group.hard_constraint_cooperation),
        ].filter(Boolean).join('');
        if (groupFields) {
            html += `<div class="cc-group-info">${groupFields}</div>`;
        }

        // 团队成员
        if (members.length > 0) {
            const memberCards = members.map(m => {
                // 尝试从角色列表中查找角色名
                let memberName = '';
                if (m.character_id) {
                    const found = characters.find(ch => ch.card.id === m.character_id);
                    if (found) memberName = found.card.name;
                }
                return `<div class="cc-member-card">
                    <div class="cc-member-name">${memberName || '未知角色'}</div>
                    ${m.role ? `<div class="cc-member-role">${m.role}</div>` : ''}
                    ${m.main_line_contribution ? `<div class="cc-member-field"><span class="cc-member-label">主线贡献：</span>${m.main_line_contribution}</div>` : ''}
                    ${m.key_flaw ? `<div class="cc-member-field"><span class="cc-member-label">关键缺陷：</span>${m.key_flaw}</div>` : ''}
                    ${m.key_ability ? `<div class="cc-member-field"><span class="cc-member-label">关键能力：</span>${m.key_ability}</div>` : ''}
                </div>`;
            }).join('');
            html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-user-friends"></i> 团队成员 (${members.length})</div><div class="cc-member-grid">${memberCards}</div></div>`;
        }

        // 团队成长弧线
        if (arcs.length > 0) {
            const arcItems = arcs.map((a, idx) => {
                const isLast = idx === arcs.length - 1;
                return `<div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                    <div class="ws-timeline-dot"></div>
                    <div class="ws-timeline-content">
                        ${a.stage ? `<div class="ws-timeline-era">${a.stage}</div>` : ''}
                        <div class="ws-timeline-event">${a.description || ''}</div>
                    </div>
                </div>`;
            }).join('');
            html += `<div class="cc-subsection"><div class="cc-subsection-title"><i class="fas fa-route"></i> 团队成长弧线 (${arcs.length})</div><div class="ws-timeline">${arcItems}</div></div>`;
        }

        html += `</div>`; // webnovel-section end
    });

    html += '</div>';
    container.innerHTML = html;
}

// ══════════ 金手指选项卡渲染 ══════════

function renderGoldenFinger(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.golden_finger) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-hand-sparkles"></i>
                <p>暂无金手指数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const gf = data.golden_finger;
    const upgrades = data.upgrades || [];
    const payoffs = data.payoffs || [];
    const feedbacks = data.feedbacks || [];

    const gridItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-info-item">
            <span class="webnovel-info-label">${label}</span>
            <span class="webnovel-info-value">${value}</span>
        </div>`;
    };
    const detailItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-detail-item"><span class="webnovel-detail-label">${label}</span><span>${value}</span></div>`;
    };

    let html = '<div class="webnovel-worldview">';

    // ── 金手指基本信息 ──
    html += `<div class="webnovel-section">`;
    html += `<div class="webnovel-section-title"><i class="fas fa-hand-sparkles"></i> 金手指设定</div>`;

    const basicGrid = [
        gridItem('类型', gf.type),
        gridItem('题材契合度', gf.genre_fit),
        gridItem('主要作用', gf.main_role),
        gridItem('可见性', gf.visibility),
        gridItem('核心功能', gf.core_function),
        gridItem('视觉表现', gf.visual_expression),
        gridItem('触发条件', gf.trigger_condition),
        gridItem('获取事件', gf.acquisition_event),
    ].filter(Boolean).join('');
    if (basicGrid) {
        html += `<div class="webnovel-info-grid">${basicGrid}</div>`;
    }
    html += `</div>`;

    // ── 代价与约束 ──
    const costFields = [
        detailItem('代价限制：', gf.cost_limitation),
        detailItem('不可逆代价：', gf.irreversible_cost),
        detailItem('冷却限制：', gf.cooldown_limit),
        detailItem('禁忌事项：', gf.forbidden_items),
        detailItem('失败惩罚：', gf.failure_penalty),
        detailItem('克制方法：', gf.counter_method),
        detailItem('反套路契合：', gf.anti_trope_alignment),
        detailItem('硬约束绑定：', gf.hard_constraint_binding),
        detailItem('主角缺陷影响：', gf.protagonist_flaw_effect),
    ].filter(Boolean).join('');
    if (costFields) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-balance-scale"></i> 代价与约束</div>`;
        html += costFields;
        html += `</div>`;
    }

    // ── 升级路线 ──
    if (upgrades.length > 0) {
        const upgradeItems = upgrades.map((u, idx) => {
            const isLast = idx === upgrades.length - 1;
            return `<div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                <div class="ws-timeline-dot"></div>
                <div class="ws-timeline-content">
                    ${u.stage ? `<div class="ws-timeline-era">${u.stage}</div>` : ''}
                    <div class="ws-timeline-event">${u.description || ''}</div>
                </div>
            </div>`;
        }).join('');
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-arrow-up"></i> 升级路线 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${upgrades.length}阶)</span></div>`;
        html += `<div class="ws-timeline">${upgradeItems}</div>`;
        html += `</div>`;
    }

    // ── 爽点设计 ──
    if (payoffs.length > 0) {
        const payoffCards = payoffs.map(p => {
            return `<div class="gf-payoff-card">
                ${p.type ? `<span class="gf-payoff-type">${p.type}</span>` : ''}
                ${p.description ? `<div class="gf-payoff-desc">${p.description}</div>` : ''}
            </div>`;
        }).join('');
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-star"></i> 爽点设计 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${payoffs.length}个)</span></div>`;
        html += `<div class="gf-payoff-grid">${payoffCards}</div>`;
        html += `</div>`;
    }

    // ── 反馈节奏 ──
    if (feedbacks.length > 0) {
        const feedbackItems = feedbacks.map(f => {
            return `<div class="gf-feedback-item">
                <div class="gf-feedback-header">
                    ${f.type ? `<span class="gf-feedback-type">${f.type}</span>` : ''}
                    ${f.chapter_interval ? `<span class="gf-feedback-interval">每${f.chapter_interval}章</span>` : ''}
                </div>
                ${f.description ? `<div class="gf-feedback-desc">${f.description}</div>` : ''}
            </div>`;
        }).join('');
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-redo"></i> 反馈节奏 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${feedbacks.length}个)</span></div>`;
        html += feedbackItems;
        html += `</div>`;
    }

    // 无子数据时的提示
    if (upgrades.length === 0 && payoffs.length === 0 && feedbacks.length === 0) {
        html += `<div class="webnovel-section" style="text-align:center; color:var(--neu-text-muted);">
            <i class="fas fa-info-circle" style="margin-right:4px;"></i>
            升级路线、爽点设计和反馈节奏尚未生成
        </div>`;
    }

    html += '</div>';
    container.innerHTML = html;
}

// ══════════ 时间线选项卡渲染 ══════════

function renderTimeline(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.timelines || data.timelines.length === 0) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-clock"></i>
                <p>暂无时间线数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行章节规划</p>
            </div>
        `;
        return;
    }

    const timelines = data.timelines;

    let html = '<div class="webnovel-worldview">';

    timelines.forEach((item, idx) => {
        const tl = item.timeline;
        const chapters = item.chapters || [];
        const countdowns = item.countdowns || [];

        // ── 时间线基本信息 ──
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-clock"></i> 第${tl.volume_number || (idx + 1)}卷 时间线</div>`;

        const infoGrid = [];
        if (tl.time_base) infoGrid.push(`<div class="webnovel-info-item"><span class="webnovel-info-label">时间基准</span><span class="webnovel-info-value">${tl.time_base}</span></div>`);
        if (tl.time_span) infoGrid.push(`<div class="webnovel-info-item"><span class="webnovel-info-label">时间跨度</span><span class="webnovel-info-value">${tl.time_span}</span></div>`);
        if (tl.countdown_events) infoGrid.push(`<div class="webnovel-info-item"><span class="webnovel-info-label">倒计时事件</span><span class="webnovel-info-value">${tl.countdown_events}</span></div>`);
        if (infoGrid.length > 0) {
            html += `<div class="webnovel-info-grid">${infoGrid.join('')}</div>`;
        }
        html += `</div>`;

        // ── 章节时间轴 ──
        if (chapters.length > 0) {
            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-list-ol"></i> 章节时间轴 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${chapters.length}章)</span></div>`;

            // 章节较多时用表格展示更紧凑
            html += `<div class="tl-chapter-table">`;
            html += `<div class="tl-table-header">`;
            html += `<span class="tl-col-chapter">章节</span>`;
            html += `<span class="tl-col-anchor">时间锚点</span>`;
            html += `<span class="tl-col-duration">时长</span>`;
            html += `<span class="tl-col-interval">间隔</span>`;
            html += `<span class="tl-col-notes">备注</span>`;
            html += `</div>`;

            chapters.forEach(ch => {
                html += `<div class="tl-table-row">`;
                html += `<span class="tl-col-chapter tl-col-bold">第${ch.chapter_number}章</span>`;
                html += `<span class="tl-col-anchor">${ch.time_anchor || '-'}</span>`;
                html += `<span class="tl-col-duration">${ch.chapter_duration || '-'}</span>`;
                html += `<span class="tl-col-interval">${ch.interval_from_prev || '-'}</span>`;
                html += `<span class="tl-col-notes">${ch.notes || ch.countdown_status || '-'}</span>`;
                html += `</div>`;
            });

            html += `</div>`; // tl-chapter-table
            html += `</div>`; // webnovel-section
        }

        // ── 倒计时事件 ──
        if (countdowns.length > 0) {
            const countdownCards = countdowns.map(cd => {
                return `<div class="tl-countdown-card">
                    <div class="tl-countdown-header">
                        <span class="tl-countdown-name">${cd.event_name || '未命名'}</span>
                        ${cd.start_countdown ? `<span class="tl-countdown-badge">${cd.start_countdown}</span>` : ''}
                    </div>
                    ${cd.current_status ? `<div class="tl-countdown-field"><span class="tl-countdown-label">当前状态：</span>${cd.current_status}</div>` : ''}
                    ${cd.trigger_chapter ? `<div class="tl-countdown-field"><span class="tl-countdown-label">触发章节：</span>第${cd.trigger_chapter}章</div>` : ''}
                    ${cd.result ? `<div class="tl-countdown-field"><span class="tl-countdown-label">结果：</span>${cd.result}</div>` : ''}
                </div>`;
            }).join('');

            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-hourglass-end"></i> 倒计时事件 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${countdowns.length}个)</span></div>`;
            html += `<div class="tl-countdown-grid">${countdownCards}</div>`;
            html += `</div>`;
        }

        // 无子数据时提示
        if (chapters.length === 0 && countdowns.length === 0) {
            html += `<div class="webnovel-section" style="text-align:center; color:var(--neu-text-muted);">
                <i class="fas fa-info-circle" style="margin-right:4px;"></i>
                本卷尚未生成章节时间轴和倒计时事件
            </div>`;
        }
    });

    html += '</div>';
    container.innerHTML = html;
}

// ══════════ 反派选项卡渲染 ══════════

function renderVillain(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.villains || data.villains.length === 0) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-skull-crossbones"></i>
                <p>暂无反派数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const villains = data.villains;

    const gridItem = (label, value) => {
        if (!value && value !== 0) return '';
        const display = (value === 1 ? '是' : value === 0 ? '否' : value);
        return `<div class="webnovel-info-item">
            <span class="webnovel-info-label">${label}</span>
            <span class="webnovel-info-value">${display}</span>
        </div>`;
    };
    const detailItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-detail-item"><span class="webnovel-detail-label">${label}</span><span>${value}</span></div>`;
    };

    let html = '<div class="webnovel-worldview">';

    villains.forEach((item, idx) => {
        const v = item.villain;
        const hierarchy = item.hierarchy || [];
        const plotNodes = item.plot_nodes || [];

        // ── 反派基本信息 ──
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-skull-crossbones"></i> ${v.name || '反派' + (idx + 1)} 设定</div>`;

        const basicGrid = [
            gridItem('身份/势力', v.identity_faction),
            gridItem('登场时机', v.appearance_timing),
            gridItem('核心欲望', v.core_desire),
            gridItem('核心恐惧', v.core_fear),
            gridItem('行动原则', v.action_principle),
            gridItem('共有欲望/缺陷', v.shared_desire_flaw),
            gridItem('反派路径', v.villain_path),
            gridItem('价值冲突点', v.value_conflict_points),
        ].filter(Boolean).join('');
        if (basicGrid) {
            html += `<div class="webnovel-info-grid">${basicGrid}</div>`;
        }
        html += `</div>`;

        // ── 力量与约束 ──
        const powerFields = [
            detailItem('力量等级：', v.power_level),
            detailItem('关键能力：', v.key_abilities),
            detailItem('组织资源：', v.organization_resources),
            detailItem('限制规则：', v.restricted_rules),
            detailItem('代价机制：', v.cost_mechanism),
            detailItem('克制点：', v.counter_points),
            detailItem('升级节奏：', v.upgrade_rhythm),
            detailItem('力量阶梯：', v.power_ladder),
        ].filter(Boolean).join('');
        if (powerFields) {
            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-fist-raised"></i> 力量与约束</div>`;
            html += powerFields;
            html += `</div>`;
        }

        // ── 特殊属性 ──
        const specialFlags = [];
        if (v.can_be_redeemed) specialFlags.push(`<span class="vl-flag vl-flag-red">可洗白</span>`);
        if (v.has_higher_villain) specialFlags.push(`<span class="vl-flag vl-flag-purple">幕后黑手</span>`);
        if (specialFlags.length > 0) {
            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-tags"></i> 特殊属性</div>`;
            html += `<div class="vl-flag-row">${specialFlags.join('')}</div>`;
            html += `</div>`;
        }

        // ── 反派层级 ──
        if (hierarchy.length > 0) {
            const tierCards = hierarchy.map(h => {
                const tierClass = {'终极': 'vl-tier-ultimate', '一流': 'vl-tier-high', '二流': 'vl-tier-mid', '小喽啰': 'vl-tier-low'}[h.tier] || 'vl-tier-mid';
                return `<div class="vl-hierarchy-card">
                    <div class="vl-hierarchy-header">
                        <span class="vl-hierarchy-name">${h.villain_name || '未命名'}</span>
                        ${h.tier ? `<span class="vl-hierarchy-tier ${tierClass}">${h.tier}</span>` : ''}
                    </div>
                    ${h.stage ? `<div class="vl-hierarchy-field"><span class="vl-hierarchy-label">阶段：</span>${h.stage}</div>` : ''}
                    ${h.goal ? `<div class="vl-hierarchy-field"><span class="vl-hierarchy-label">目标：</span>${h.goal}</div>` : ''}
                    ${h.protagonist_relation ? `<div class="vl-hierarchy-field"><span class="vl-hierarchy-label">与主角关系：</span>${h.protagonist_relation}</div>` : ''}
                </div>`;
            }).join('');

            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-layer-group"></i> 反派层级 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${hierarchy.length}个)</span></div>`;
            html += `<div class="vl-hierarchy-grid">${tierCards}</div>`;
            html += `</div>`;
        }

        // ── 剧情节点 ──
        if (plotNodes.length > 0) {
            const nodeItems = plotNodes.map((n, nIdx) => {
                const isLast = nIdx === plotNodes.length - 1;
                const typeLabel = {'turning_point': '转折点', 'climax': '高潮', 'appearance': '登场', 'escalation': '升级', 'defeat': '败北', 'reveal': '揭露'}[n.node_type] || n.node_type;
                return `<div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                    <div class="ws-timeline-dot"></div>
                    <div class="ws-timeline-content">
                        <div class="ws-timeline-era">${n.chapter ? '第' + n.chapter + '章' : ''} ${typeLabel}</div>
                        <div class="ws-timeline-event">${n.description || ''}</div>
                    </div>
                </div>`;
            }).join('');

            html += `<div class="webnovel-section">`;
            html += `<div class="webnovel-section-title"><i class="fas fa-route"></i> 剧情节点 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${plotNodes.length}个)</span></div>`;
            html += `<div class="ws-timeline">${nodeItems}</div>`;
            html += `</div>`;
        }

        // 无子数据时提示
        if (hierarchy.length === 0 && plotNodes.length === 0) {
            html += `<div class="webnovel-section" style="text-align:center; color:var(--neu-text-muted);">
                <i class="fas fa-info-circle" style="margin-right:4px;"></i>
                反派层级和剧情节点尚未生成
            </div>`;
        }
    });

    html += '</div>';
    container.innerHTML = html;
}

function renderPowerSystem(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.power_system) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-bolt"></i>
                <p>暂无战力体系数据</p>
                <p style="font-size: 11px; margin-top: 4px;">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const ps = data.power_system;
    const levels = data.levels || [];
    const feedbacks = data.feedbacks || [];

    const gridItem = (label, value) => {
        if (!value && value !== 0) return '';
        return `<div class="webnovel-info-item">
            <span class="webnovel-info-label">${label}</span>
            <span class="webnovel-info-value">${value}</span>
        </div>`;
    };
    const detailItem = (label, value) => {
        if (!value) return '';
        return `<div class="webnovel-detail-item"><span class="webnovel-detail-label">${label}</span><span>${value}</span></div>`;
    };

    let html = '<div class="webnovel-worldview">';

    // ── 核心设定 ──
    const coreGrid = [
        gridItem('体系类型', ps.system_type),
        gridItem('核心信条', ps.core_creed),
        gridItem('公平原则', ps.fairness_principle),
        gridItem('代价规则', ps.cost_rules),
        gridItem('能量来源', ps.energy_source),
        gridItem('修炼方式', ps.training_methods),
    ].filter(Boolean).join('');
    if (coreGrid) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-bolt"></i> 核心设定</div>`;
        html += `<div class="webnovel-info-grid">${coreGrid}</div>`;
        html += `</div>`;
    }

    // ── 境界体系 ──
    const realmGrid = [
        gridItem('典型境界链', ps.typical_realm_chain),
        gridItem('小境界划分', ps.small_realm_divisions),
        gridItem('替代路径', ps.alternative_paths),
    ].filter(Boolean).join('');
    if (realmGrid) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-stairs"></i> 境界体系</div>`;
        html += `<div class="webnovel-info-grid">${realmGrid}</div>`;
        html += `</div>`;
    }

    // ── 资源与经济 ──
    const resourceGrid = [
        gridItem('资源类型', ps.resource_types),
        gridItem('资源获取', ps.resource_acquisition),
        gridItem('稀缺规则', ps.scarcity_rules),
        gridItem('社会控制机制', ps.social_control_mechanism),
    ].filter(Boolean).join('');
    if (resourceGrid) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-gem"></i> 资源与经济</div>`;
        html += `<div class="webnovel-info-grid">${resourceGrid}</div>`;
        html += `</div>`;
    }

    // ── 战斗体系 ──
    const combatFields = [
        detailItem('伤害防御逻辑：', ps.damage_defense_logic),
        detailItem('战斗节奏：', ps.battle_rhythm),
        detailItem('克制关系：', ps.counter_relations),
        detailItem('逃脱机制：', ps.escape_mechanism),
    ].filter(Boolean).join('');
    if (combatFields) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-shield-halved"></i> 战斗体系</div>`;
        html += combatFields;
        html += `</div>`;
    }

    // ── 限制与约束 ──
    const limitFields = [
        detailItem('禁忌术法：', ps.forbidden_arts),
        detailItem('高阶限制：', ps.high_level_limits),
        detailItem('硬限制：', ps.hard_limits),
        detailItem('体系漏洞：', ps.system_vulnerabilities),
        detailItem('反套路设计：', ps.anti_trope_alignment),
        detailItem('硬约束绑定：', ps.hard_constraint_binding),
    ].filter(Boolean).join('');
    if (limitFields) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-lock"></i> 限制与约束</div>`;
        html += limitFields;
        html += `</div>`;
    }

    // ── 剧情利用 ──
    const plotFields = [
        detailItem('主角利用：', ps.protagonist_exploitation),
        detailItem('反派克制：', ps.villain_counter),
    ].filter(Boolean).join('');
    if (plotFields) {
        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-chess"></i> 剧情利用</div>`;
        html += plotFields;
        html += `</div>`;
    }

    // ── 等级体系 ──
    if (levels.length > 0) {
        const levelCards = levels.map((lv, idx) => {
            const fields = [];
            if (lv.core_abilities) fields.push(`<div class="ps-level-field"><span class="ps-level-label">核心能力：</span>${lv.core_abilities}</div>`);
            if (lv.resource_requirements) fields.push(`<div class="ps-level-field"><span class="ps-level-label">资源需求：</span>${lv.resource_requirements}</div>`);
            if (lv.breakthrough_method) fields.push(`<div class="ps-level-field"><span class="ps-level-label">突破方式：</span>${lv.breakthrough_method}</div>`);
            if (lv.failure_cost) fields.push(`<div class="ps-level-field"><span class="ps-level-label">失败代价：</span>${lv.failure_cost}</div>`);
            if (lv.overlevel_cost) fields.push(`<div class="ps-level-field"><span class="ps-level-label">越级代价：</span>${lv.overlevel_cost}</div>`);
            return `<div class="ps-level-card">
                <div class="ps-level-header">
                    <span class="ps-level-order">${idx + 1}</span>
                    <span class="ps-level-name">${lv.level_name || '未命名'}</span>
                </div>
                ${fields.length > 0 ? `<div class="ps-level-body">${fields.join('')}</div>` : ''}
            </div>`;
        }).join('');

        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-layer-group"></i> 等级体系 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${levels.length}级)</span></div>`;
        html += `<div class="ps-level-list">${levelCards}</div>`;
        html += `</div>`;
    }

    // ── 反馈节奏 ──
    if (feedbacks.length > 0) {
        const fbItems = feedbacks.map((fb, idx) => {
            const isLast = idx === feedbacks.length - 1;
            return `<div class="ws-timeline-item ${isLast ? 'ws-timeline-last' : ''}">
                <div class="ws-timeline-dot"></div>
                <div class="ws-timeline-content">
                    <div class="ws-timeline-era">${fb.realm_change_chapter ? '第' + fb.realm_change_chapter + '章' : '境界变化'}</div>
                    <div class="ws-timeline-event">${fb.power_gap_display || ''}</div>
                </div>
            </div>`;
        }).join('');

        html += `<div class="webnovel-section">`;
        html += `<div class="webnovel-section-title"><i class="fas fa-wave-square"></i> 反馈节奏 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${feedbacks.length}个)</span></div>`;
        html += `<div class="ws-timeline">${fbItems}</div>`;
        html += `</div>`;
    }

    // 无子数据时提示
    if (levels.length === 0 && feedbacks.length === 0) {
        html += `<div class="webnovel-section" style="text-align:center; color:var(--neu-text-muted);">
            <i class="fas fa-info-circle" style="margin-right:4px;"></i>
            等级体系和反馈节奏尚未生成
        </div>`;
    }

    html += '</div>';
    container.innerHTML = html;
}

function renderCoolPoints(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.cool_points || data.cool_points.length === 0) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-fire"></i>
                <p>暂无爽点记录</p>
                <p style="font-size: 11px; margin-top: 4px;">创作后生成</p>
            </div>
        `;
        return;
    }

    const points = data.cool_points;
    const typeLabels = {
        'face_slap': '打脸', 'reversal': '逆转', 'power_up': '升级突破',
        'show_off': '装逼', 'revenge': '复仇', 'romance': '感情',
        'conspiracy_reveal': '阴谋揭露', 'battle': '战斗高潮'
    };

    let html = '<div class="webnovel-worldview">';
    html += `<div class="webnovel-section">`;
    html += `<div class="webnovel-section-title"><i class="fas fa-fire"></i> 爽点记录 <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${points.length}个)</span></div>`;

    const cards = points.map((cp, idx) => {
        const typeLabel = typeLabels[cp.cool_point_type] || cp.cool_point_type || '未分类';
        const bars = [];
        if (cp.pressure_level) bars.push(`<div class="cp-stat"><span class="cp-stat-label">压抑</span><div class="cp-bar"><div class="cp-bar-fill cp-bar-pressure" style="width:${Math.min(cp.pressure_level * 10, 100)}%"></div></div><span class="cp-stat-val">${cp.pressure_level}</span></div>`);
        if (cp.release_level) bars.push(`<div class="cp-stat"><span class="cp-stat-label">释放</span><div class="cp-bar"><div class="cp-bar-fill cp-bar-release" style="width:${Math.min(cp.release_level * 10, 100)}%"></div></div><span class="cp-stat-val">${cp.release_level}</span></div>`);
        if (cp.impact_score) bars.push(`<div class="cp-stat"><span class="cp-stat-label">冲击</span><div class="cp-bar"><div class="cp-bar-fill cp-bar-impact" style="width:${Math.min(cp.impact_score * 10, 100)}%"></div></div><span class="cp-stat-val">${cp.impact_score}</span></div>`);

        return `<div class="cp-card">
            <div class="cp-card-header">
                <span class="cp-chapter">第${cp.chapter_number}章</span>
                <span class="cp-type-badge">${typeLabel}</span>
                ${cp.impact_score ? `<span class="cp-impact">★ ${cp.impact_score}</span>` : ''}
            </div>
            ${cp.content ? `<div class="cp-content">${cp.content}</div>` : ''}
            <div class="cp-meta">
                ${cp.execution_mode ? `<span class="cp-meta-item"><i class="fas fa-cog"></i> ${cp.execution_mode}</span>` : ''}
                ${cp.structure_stage ? `<span class="cp-meta-item"><i class="fas fa-layer-group"></i> ${cp.structure_stage}</span>` : ''}
                ${cp.reader_emotion ? `<span class="cp-meta-item"><i class="fas fa-heart"></i> ${cp.reader_emotion}</span>` : ''}
            </div>
            ${bars.length > 0 ? `<div class="cp-bars">${bars.join('')}</div>` : ''}
            ${cp.evidence ? `<div class="cp-evidence"><i class="fas fa-quote-left"></i> ${cp.evidence}</div>` : ''}
        </div>`;
    }).join('');

    html += `<div class="cp-list">${cards}</div>`;
    html += `</div>`;
    html += '</div>';
    container.innerHTML = html;
}

function renderOpenLoops(data) {
    const container = document.getElementById('worldContent');

    if (!data || !data.success || !data.loops || data.loops.length === 0) {
        container.innerHTML = `
            <div class="world-empty">
                <i class="fas fa-puzzle-piece"></i>
                <p>暂无开放悬念</p>
                <p style="font-size: 11px; margin-top: 4px;">创作后生成</p>
            </div>
        `;
        return;
    }

    const loops = data.loops;
    const statusLabels = { active: '进行中', resolved: '已解决', abandoned: '已放弃' };
    const statusColors = { active: '#e74c3c', resolved: '#27ae60', abandoned: '#95a5a6' };
    const tierLabels = { '核心': '核心', '支线': '支线', '装饰': '装饰' };
    const tierColors = { '核心': '#e74c3c', '支线': '#f39c12', '装饰': '#3498db' };

    // 按状态分组
    const active = loops.filter(l => l.status === 'active');
    const resolved = loops.filter(l => l.status === 'resolved');
    const abandoned = loops.filter(l => l.status === 'abandoned');

    const renderGroup = (title, icon, items, color) => {
        if (items.length === 0) return '';
        const cards = items.map(loop => {
            const tierColor = tierColors[loop.tier] || '#95a5a6';
            const urgencyPct = Math.min((loop.urgency || 0) * 33, 100);
            return `<div class="ol-card">
                <div class="ol-card-header">
                    ${loop.tier ? `<span class="ol-tier-badge" style="background:${tierColor}20;color:${tierColor}">${loop.tier}</span>` : ''}
                    ${loop.urgency ? `<span class="ol-urgency">紧急度 ${(loop.urgency || 0).toFixed(1)}</span>` : ''}
                </div>
                ${loop.content ? `<div class="ol-content">${loop.content}</div>` : ''}
                <div class="ol-meta">
                    ${loop.planted_chapter ? `<span class="ol-meta-item"><i class="fas fa-seedling"></i> 埋设: 第${loop.planted_chapter}章</span>` : ''}
                    ${loop.target_chapter ? `<span class="ol-meta-item"><i class="fas fa-bullseye"></i> 目标: 第${loop.target_chapter}章</span>` : ''}
                    ${loop.resolved_chapter ? `<span class="ol-meta-item"><i class="fas fa-check-circle"></i> 解决: 第${loop.resolved_chapter}章</span>` : ''}
                </div>
                ${loop.urgency ? `<div class="ol-urgency-bar"><div class="ol-urgency-fill" style="width:${urgencyPct}%;background:${color}"></div></div>` : ''}
                ${loop.evidence ? `<div class="ol-evidence"><i class="fas fa-quote-left"></i> ${loop.evidence}</div>` : ''}
            </div>`;
        }).join('');

        return `<div class="webnovel-section">
            <div class="webnovel-section-title"><i class="${icon}"></i> ${title} <span style="font-weight:400;color:var(--neu-text-muted);font-size:11px;margin-left:4px;">(${items.length}个)</span></div>
            <div class="ol-list">${cards}</div>
        </div>`;
    };

    let html = '<div class="webnovel-worldview">';
    html += renderGroup('进行中', 'fas fa-spinner', active, '#e74c3c');
    html += renderGroup('已解决', 'fas fa-check-circle', resolved, '#27ae60');
    html += renderGroup('已放弃', 'fas fa-times-circle', abandoned, '#95a5a6');
    html += '</div>';
    container.innerHTML = html;
}

function showOutlineModal() {
    document.getElementById('outlineModal').style.display = 'flex';
    loadWebnovelOutline();
}

function closeOutlineModal() {
    document.getElementById('outlineModal').style.display = 'none';
    state.selectedVolumeOutlineId = null;
}

function switchOutlineTab(tab) {
    state.currentOutlineTab = tab;
    document.querySelectorAll('.outline-tab-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) event.target.classList.add('active');
    loadWebnovelOutline();
}

async function loadWebnovelOutline() {
    if (!state.scriptId) {
        renderWebnovelOutline(null);
        return;
    }
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/volume-outlines?script_id=${state.scriptId}`, { silent: true });
        renderWebnovelOutline(data);
    } catch (e) {
        console.error('加载网文卷纲失败:', e);
        renderWebnovelOutline(null);
    }
}

async function renderWebnovelOutline(data) {
    const leftPanel = document.getElementById('volumeListPanel');
    const rightPanel = document.getElementById('outlineDetailPanel');

    if (!data || !data.success) {
        leftPanel.innerHTML = '';
        rightPanel.innerHTML = `
            <div class="outline-empty">
                <i class="fas fa-book"></i>
                <p>暂无网文卷纲数据</p>
                <p class="outline-empty-hint">请先进行深度初始化</p>
            </div>
        `;
        return;
    }

    const outlines = data.outlines || [];
    state.volumeOutlines = outlines;

    // 渲染左栏：卷纲列表
    renderVolumeListPanel(outlines);

    // 自动选中第一个或保持当前选中
    if (outlines.length > 0) {
        const currentSelected = state.selectedVolumeOutlineId;
        const isValid = currentSelected && outlines.some(o => o.id === currentSelected);
        if (!isValid) {
            state.selectedVolumeOutlineId = outlines[0].id;
        }
        await renderOutlineDetailPanel(state.selectedVolumeOutlineId);
    } else {
        state.selectedVolumeOutlineId = null;
        rightPanel.innerHTML = `
            <div class="outline-empty">
                <i class="fas fa-sitemap"></i>
                <p>暂无卷纲规划</p>
                <p class="outline-empty-hint">点击左侧“添加卷纲”或“智能规划”开始</p>
            </div>
        `;
    }
}

function renderVolumeListPanel(outlines) {
    const leftPanel = document.getElementById('volumeListPanel');
    if (!outlines || outlines.length === 0) {
        leftPanel.innerHTML = `
            <div class="volume-list-empty">
                <i class="fas fa-layer-group"></i>
                <p>暂无卷纲</p>
            </div>
        `;
        return;
    }
    leftPanel.innerHTML = outlines.map(vol => {
        const isActive = state.selectedVolumeOutlineId === vol.id;
        const chapterCount = (state.volumeChapterPlans && state.volumeChapterPlans[vol.id])
            ? state.volumeChapterPlans[vol.id].length
            : (vol.chapter_end - vol.chapter_start + 1 || 0);
        return `
            <div class="volume-list-item ${isActive ? 'active' : ''}" onclick="selectVolumeOutline(${vol.id})">
                <span class="volume-list-number">${vol.volume_number || 1}</span>
                <div class="volume-list-info">
                    <div class="volume-list-name">${vol.volume_name || '未命名'}</div>
                    <div class="volume-list-meta">第${vol.chapter_start || 1}-${vol.chapter_end || '?'}章</div>
                </div>
            </div>
        `;
    }).join('');
}

async function selectVolumeOutline(volId) {
    state.selectedVolumeOutlineId = volId;
    // 更新左栏选中态
    document.querySelectorAll('.volume-list-item').forEach(el => el.classList.remove('active'));
    const items = document.querySelectorAll('.volume-list-item');
    const outlines = state.volumeOutlines || [];
    const idx = outlines.findIndex(o => o.id === volId);
    if (idx >= 0 && items[idx]) items[idx].classList.add('active');
    // 渲染右栏
    await renderOutlineDetailPanel(volId);
}

async function renderOutlineDetailPanel(volId) {
    const panel = document.getElementById('outlineDetailPanel');
    if (!volId) {
        panel.innerHTML = '<div class="outline-empty"><p>请选择一个卷纲</p></div>';
        return;
    }

    const outline = (state.volumeOutlines || []).find(o => o.id === volId);
    if (!outline) {
        panel.innerHTML = '<div class="outline-empty"><p>卷纲不存在</p></div>';
        return;
    }

    // 加载章节规划（优先用缓存）
    let chapterPlans = state.volumeChapterPlans && state.volumeChapterPlans[volId];
    if (!chapterPlans) {
        chapterPlans = await loadChapterPlans(volId);
    }

    let chaptersHtml = '';
    if (chapterPlans.length > 0) {
        chaptersHtml = chapterPlans.map(plan => `
            <div class="chapter-plan-item">
                <div class="chapter-plan-header" onclick="toggleChapterPlanDetail(${plan.id})">
                    <span class="chapter-plan-index">第${plan.chapter_index}章</span>
                    <span class="chapter-plan-title">${plan.chapter_title || '未命名'}</span>
                    <div class="chapter-plan-actions">
                        <button class="outline-action-btn" onclick="event.stopPropagation(); showChapterPlanModal(${plan.id}, ${volId})" title="编辑">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="outline-action-btn delete" onclick="event.stopPropagation(); deleteChapterPlan(${plan.id}, ${volId})" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="chapter-plan-detail" id="chapterPlanDetail-${plan.id}" style="display:none;">
                    ${plan.summary ? `<div class="chapter-plan-field"><strong>概述：</strong>${plan.summary}</div>` : ''}
                    ${plan.key_events ? `<div class="chapter-plan-field"><strong>关键事件：</strong>${plan.key_events}</div>` : ''}
                    ${plan.foreshadowing ? `<div class="chapter-plan-field"><strong>伏笔：</strong>${plan.foreshadowing}</div>` : ''}
                </div>
            </div>
        `).join('');
    } else {
        chaptersHtml = `
            <div class="chapter-plan-empty">
                <i class="fas fa-file-alt"></i>
                <p>暂无章节规划</p>
                <p class="outline-empty-hint">点击下方按钮添加或AI生成</p>
            </div>
        `;
    }

    panel.innerHTML = `
        <div class="volume-detail-section">
            <div class="volume-detail-header">
                <div class="volume-detail-title">
                    <span class="volume-detail-number">第${outline.volume_number || 1}卷</span>
                    <span class="volume-detail-name">${outline.volume_name || '未命名'}</span>
                </div>
                <div class="volume-detail-actions">
                    <button class="btn btn-xs btn-outline-primary" onclick="showVolumeOutlineModal(${outline.id})">
                        <i class="fas fa-edit"></i> 编辑卷纲
                    </button>
                    <button class="btn btn-xs btn-outline-danger" onclick="deleteVolumeOutline(${outline.id})">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            </div>
            <div class="volume-detail-info">
                <span><i class="fas fa-file-alt"></i> 章节 ${outline.chapter_start || 1} - ${outline.chapter_end || '?'}</span>
            </div>
            ${outline.core_conflict ? `<div class="volume-detail-field"><strong>核心冲突：</strong>${outline.core_conflict}</div>` : ''}
            ${outline.volume_climax ? `<div class="volume-detail-field"><strong>卷末高潮：</strong>${outline.volume_climax}</div>` : ''}
            ${outline.promise_description ? `<div class="volume-detail-field"><strong>开卷承诺：</strong>${outline.promise_description}</div>` : ''}
        </div>
        <div class="chapter-plan-section">
            <div class="chapter-plan-header-bar">
                <span class="chapter-plan-section-title"><i class="fas fa-list-ol"></i> 章节规划 (${chapterPlans.length}章)</span>
                <div class="chapter-plan-section-actions">
                    <button class="btn btn-xs btn-outline-secondary" onclick="showChapterPlanModal(null, ${volId})">
                        <i class="fas fa-plus"></i> 添加
                    </button>
                    <button class="btn btn-xs btn-outline-success" onclick="splitVolumeToChapters(${volId})">
                        <i class="fas fa-magic"></i> 智能拆章
                    </button>
                </div>
            </div>
            <div class="chapter-plan-list">
                ${chaptersHtml}
            </div>
        </div>
    `;
}

function toggleChapterPlanDetail(planId) {
    const detail = document.getElementById(`chapterPlanDetail-${planId}`);
    if (detail) {
        const isHidden = detail.style.display === 'none' || !detail.style.display;
        detail.style.display = isHidden ? 'block' : 'none';
    }
}

async function loadChapterPlans(volumeOutlineId) {
    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/chapter-plans?script_id=${state.scriptId}&volume_outline_id=${volumeOutlineId}`, { silent: true });
        const plans = data.success ? (data.chapter_plans || data.plans || []) : [];
        // 缓存到 state
        if (!state.volumeChapterPlans) state.volumeChapterPlans = {};
        state.volumeChapterPlans[volumeOutlineId] = plans;
        return plans;
    } catch (e) {
        console.error('加载章纲失败:', e);
        return [];
    }
}

function splitVolumeToChapters(outlineId) {
    const outline = (state.volumeOutlines || []).find(o => o.id === outlineId);
    if (!outline) {
        showToast('卷纲不存在', 'error');
        return;
    }
    const voStart = outline.chapter_start || 1;
    const voEnd = outline.chapter_end || (voStart + 29);

    // 计算已规划章节，用于构建起始章节下拉选项
    const cachedPlans = (state.volumeChapterPlans && state.volumeChapterPlans[outlineId]) || [];
    const plannedIndices = new Set(cachedPlans.map(p => p.chapter_index));
    const maxPlanned = plannedIndices.size > 0 ? Math.max(...plannedIndices) : 0;

    // 构建起始章节有效选项：卷首 + 已规划章节 + 已规划最大+1
    const startSelect = document.getElementById('aiSplitStartChapter');
    const validStarts = new Set();
    validStarts.add(voStart);
    cachedPlans.forEach(p => validStarts.add(p.chapter_index));
    if (maxPlanned > 0 && maxPlanned + 1 <= voEnd) {
        validStarts.add(maxPlanned + 1);
    }
    const sortedStarts = Array.from(validStarts).sort((a, b) => a - b);
    startSelect.innerHTML = sortedStarts.map(n => {
        let label = `第${n}章`;
        if (n === voStart) label += '（卷首）';
        else if (n === maxPlanned + 1 && maxPlanned > 0) label += '（续写）';
        else if (plannedIndices.has(n)) label += '（已规划）';
        return `<option value="${n}">${label}</option>`;
    }).join('');

    // 更新范围提示
    let hintExtra = '';
    if (maxPlanned > 0) {
        hintExtra = `。已规划至第${maxPlanned}章`;
    }
    document.getElementById('aiSplitOutlineId').value = outlineId;
    document.getElementById('aiSplitRangeHint').textContent = `第${voStart}章 - 第${voEnd}章${hintExtra}`;

    // 填充结束章节下拉框（从当前起始值到卷纲末尾）
    _populateEndChapterSelect(voStart, voEnd);

    document.getElementById('aiSplitChapterModal').style.display = 'flex';
}

/** 根据起始章节填充结束章节下拉框 */
function _populateEndChapterSelect(startVal, voEnd) {
    const endSelect = document.getElementById('aiSplitEndChapter');
    const startNum = parseInt(startVal);
    let opts = '';
    for (let i = startNum; i <= voEnd; i++) {
        opts += `<option value="${i}">第${i}章</option>`;
    }
    endSelect.innerHTML = opts;
    // 默认选中最后一章
    endSelect.value = voEnd;
}

/** 起始章节变更时联动更新结束章节下拉框 */
function onAiSplitStartChange() {
    const outlineId = parseInt(document.getElementById('aiSplitOutlineId').value);
    const outline = (state.volumeOutlines || []).find(o => o.id === outlineId);
    if (!outline) return;
    const voEnd = outline.chapter_end || ((outline.chapter_start || 1) + 29);
    const startVal = document.getElementById('aiSplitStartChapter').value;
    _populateEndChapterSelect(startVal, voEnd);
}

function closeAiSplitChapterModal() {
    document.getElementById('aiSplitChapterModal').style.display = 'none';
}

async function confirmAiSplitChapter() {
    const outlineId = parseInt(document.getElementById('aiSplitOutlineId').value);
    const startChapter = parseInt(document.getElementById('aiSplitStartChapter').value);
    const endChapter = parseInt(document.getElementById('aiSplitEndChapter').value);

    // 构建查询参数
    const params = new URLSearchParams({
        script_id: state.scriptId,
        outline_id: outlineId,
        start_chapter: startChapter,
        end_chapter: endChapter
    });

    closeAiSplitChapterModal();
    showToast('智能拆章已启动，正在后台生成...', 'info');

    try {
        const data = await apiRequest(`/api/books/scripts/volume-outlines/split-chapter?${params.toString()}`, {
            method: 'POST',
            errorPrefix: '智能拆章失败'
        });
        if (!data.success) {
            showToast(data.detail || data.message || '智能拆章启动失败', 'error');
        }
        // 成功时不立即刷新，等待 WebSocket 通知后再刷新
    } catch (e) {
        console.error('智能拆章失败:', e);
        showToast('智能拆章失败', 'error');
    }
}

function showChapterPlanModal(planId = null, outlineId = null) {
    if (outlineId) {
        document.getElementById('chapterPlanOutlineId').value = outlineId;
    }
    document.getElementById('chapterPlanModalTitle').textContent = planId ? '编辑章节规划' : '添加章节规划';

    // 从缓存中查找章节规划
    const volId = outlineId || parseInt(document.getElementById('chapterPlanOutlineId').value);
    const cachedPlans = (state.volumeChapterPlans && state.volumeChapterPlans[volId]) || [];

    if (planId) {
        const plan = cachedPlans.find(p => p.id === planId);
        if (plan) {
            document.getElementById('chapterPlanId').value = plan.id;
            document.getElementById('chapterPlanOutlineId').value = plan.volume_outline_id || plan.outline_id || volId;
            document.getElementById('chapterPlanIndex').value = plan.chapter_index;
            document.getElementById('chapterPlanTitle').value = plan.chapter_title || '';
            document.getElementById('chapterPlanSummary').value = plan.summary || '';
            document.getElementById('chapterPlanKeyEvents').value = Array.isArray(plan.key_events) ? plan.key_events.join(', ') : (plan.key_events || '');
            document.getElementById('chapterPlanForeshadowing').value = plan.foreshadowing || '';
        }
    } else {
        document.getElementById('chapterPlanId').value = '';
        const outline = (state.volumeOutlines || []).find(o => o.id === volId);
        let nextIndex = 1;
        if (outline) {
            nextIndex = cachedPlans.length > 0
                ? Math.max(...cachedPlans.map(p => p.chapter_index)) + 1
                : outline.chapter_start || 1;
        }
        document.getElementById('chapterPlanIndex').value = nextIndex;
        document.getElementById('chapterPlanTitle').value = '';
        document.getElementById('chapterPlanSummary').value = '';
        document.getElementById('chapterPlanKeyEvents').value = '';
        document.getElementById('chapterPlanForeshadowing').value = '';
    }
    document.getElementById('chapterPlanModal').style.display = 'flex';
}

function closeChapterPlanModal() {
    document.getElementById('chapterPlanModal').style.display = 'none';
}

async function saveChapterPlan() {
    const id = document.getElementById('chapterPlanId').value;
    const outlineId = parseInt(document.getElementById('chapterPlanOutlineId').value);
    const chapterIndex = parseInt(document.getElementById('chapterPlanIndex').value) || 1;
    const title = document.getElementById('chapterPlanTitle').value.trim();
    const summary = document.getElementById('chapterPlanSummary').value.trim();
    const keyEvents = document.getElementById('chapterPlanKeyEvents').value.trim();
    const foreshadowing = document.getElementById('chapterPlanForeshadowing').value.trim();

    try {
        const url = id
                ? `/api/books/scripts/chapter-plans?script_id=${state.scriptId}&outline_id=${outlineId}&plan_id=${id}`
                : `/api/books/scripts/chapter-plans?script_id=${state.scriptId}&outline_id=${outlineId}`;
        const method = id ? 'PUT' : 'POST';
        const body = JSON.stringify({
            chapter_index: chapterIndex,
            chapter_title: title,
            summary: summary,
            key_events: keyEvents,
            foreshadowing: foreshadowing
        });
        await apiRequest(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body,
            errorPrefix: '保存失败'
        });
        closeChapterPlanModal();
        // 清除缓存并刷新右栏
        if (state.volumeChapterPlans) delete state.volumeChapterPlans[outlineId];
        await renderOutlineDetailPanel(outlineId);
        showToast('保存成功', 'success');
    } catch (e) {
        console.error('保存章节规划失败:', e);
        showToast('保存失败', 'error');
    }
}

async function deleteChapterPlan(planId, outlineId) {
    if (!confirm('确定删除此章节规划吗？')) return;
    try {
        const data = await apiRequest(`/api/books/scripts/chapter-plans?script_id=${state.scriptId}&outline_id=${outlineId}&plan_id=${planId}`, {
            method: 'DELETE',
            errorPrefix: '删除失败'
        });
        if (data.success) {
            // 清除缓存并刷新右栏
            if (state.volumeChapterPlans) delete state.volumeChapterPlans[outlineId];
            await renderOutlineDetailPanel(outlineId);
            showToast('删除成功', 'success');
        } else {
            showToast(data.message || '删除失败', 'error');
        }
    } catch (e) {
        console.error('删除章节规划失败:', e);
        showToast('删除失败', 'error');
    }
}

function selectChapterFromOutline(chapterIndex) {
    closeOutlineModal();
    selectChapter(chapterIndex);
}

function showVolumeOutlineModal(outlineId = null) {
    document.getElementById('volumeOutlineModalTitle').textContent = outlineId ? '编辑卷纲' : '添加卷纲';
    if (outlineId) {
        const outline = (state.volumeOutlines || []).find(o => o.id === outlineId);
        if (outline) {
            document.getElementById('volumeOutlineId').value = outline.id;
            document.getElementById('volumeOutlineNumber').value = outline.volume_number || 1;
            document.getElementById('volumeOutlineName').value = outline.volume_name || '';
            document.getElementById('volumeOutlineStart').value = outline.chapter_start || 1;
            document.getElementById('volumeOutlineEnd').value = outline.chapter_end || 100;
            document.getElementById('volumeOutlineConflict').value = outline.core_conflict || '';
            document.getElementById('volumeOutlineClimax').value = outline.volume_climax || '';
        }
    } else {
        document.getElementById('volumeOutlineId').value = '';
        const existing = state.volumeOutlines || [];
        const nextNumber = existing.length > 0 ? Math.max(...existing.map(o => o.volume_number || 1)) + 1 : 1;
        document.getElementById('volumeOutlineNumber').value = nextNumber;
        document.getElementById('volumeOutlineName').value = '';
        document.getElementById('volumeOutlineStart').value = '';
        document.getElementById('volumeOutlineEnd').value = '';
        document.getElementById('volumeOutlineConflict').value = '';
        document.getElementById('volumeOutlineClimax').value = '';
    }
    document.getElementById('volumeOutlineModal').style.display = 'flex';
}

function closeVolumeOutlineModal() {
    document.getElementById('volumeOutlineModal').style.display = 'none';
}

async function saveVolumeOutline() {
    const id = document.getElementById('volumeOutlineId').value;
    const volumeNumber = parseInt(document.getElementById('volumeOutlineNumber').value) || 1;
    const volumeName = document.getElementById('volumeOutlineName').value.trim();
    const startChapter = parseInt(document.getElementById('volumeOutlineStart').value) || 0;
    const endChapter = parseInt(document.getElementById('volumeOutlineEnd').value) || 0;
    const coreConflict = document.getElementById('volumeOutlineConflict').value.trim();
    const volumeClimax = document.getElementById('volumeOutlineClimax').value.trim();

    try {
        const url = id
            ? `/api/books/scripts/webnovel/volume-outlines?script_id=${state.scriptId}&outline_id=${id}`
            : `/api/books/scripts/webnovel/volume-outlines?script_id=${state.scriptId}`;
        const method = id ? 'PUT' : 'POST';
        const body = JSON.stringify({
            volume_number: volumeNumber,
            volume_title: volumeName,
            start_chapter: startChapter,
            end_chapter: endChapter,
            summary: coreConflict
        });
        const data = await apiRequest(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body,
            errorPrefix: '保存失败'
        });
        if (data.success) {
            closeVolumeOutlineModal();
            // 清除缓存并刷新
            if (id && state.volumeChapterPlans) delete state.volumeChapterPlans[parseInt(id)];
            await loadWebnovelOutline();
            showToast('保存成功', 'success');
        } else {
            showToast(data.message || '保存失败', 'error');
        }
    } catch (e) {
        console.error('保存卷纲失败:', e);
        showToast('保存失败', 'error');
    }
}

async function deleteVolumeOutline(outlineId) {
    if (!confirm('确定删除此卷纲吗？此操作将同时删除该卷下的所有章节规划。')) return;

    try {
        const data = await apiRequest(`/api/books/scripts/webnovel/volume-outlines?script_id=${state.scriptId}&outline_id=${outlineId}`, {
            method: 'DELETE',
            errorPrefix: '删除失败'
        });
        if (data.success) {
            // 清除缓存
            if (state.volumeChapterPlans) delete state.volumeChapterPlans[outlineId];
            if (state.selectedVolumeOutlineId === outlineId) {
                state.selectedVolumeOutlineId = null;
            }
            await loadWebnovelOutline();
            showToast('删除成功', 'success');
        } else {
            showToast(data.message || '删除失败', 'error');
        }
    } catch (e) {
        console.error('删除卷纲失败:', e);
        showToast('删除失败', 'error');
    }
}

async function editVolumeOutline(outlineId) {
    showVolumeOutlineModal(outlineId);
}