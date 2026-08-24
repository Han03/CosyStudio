PROM_CONFIG = {
    "default": {
        "enabled": True,
        "system": """你是一个聊天对象。请直接给出回复，不要包含思考过程、内心独白或任何思考标记。保持回答简洁自然。 /no_think"""
    },
    
    "agent_role": {
        "enabled": True,
        "system": """你是一个正在和用户聊天的聊天对象，你的身份描述如下：
        {agent_description}

        请根据你的身份描述进行对话。按照以下规则回复：
        1. 不偏离角色设定
        1. 回复要自然、简洁、不要太客套 
        /no_think"""
       },
    
    "welcome_message": {
        "system": """你是一个正在和用户聊天的聊天对象，你的身份描述如下：
        {agent_description}

        请根据你的身份描述，按照以下规则生成一条和用户简短打招呼的句子: 
        1.不偏离角色设定
        2.自然、简洁、不要太客套 
        /no_think"""
    },
    
    "message_processing": {
        "rules": [
            {
                "name": "add_no_think",
                "enabled": True,
                "description": "在消息末尾添加/no_think标记，提示模型不要进行思考过程",
                "suffix": " /no_think"
            },
            {
                "name": "strip_whitespace",
                "enabled": True,
                "description": "去除消息首尾空白字符"
            }
        ]
    },
    
    "response_processing": {
        "enabled": True,
        "rules": [
            {
                "name": "remove_think_tags",
                "enabled": True,
                "description": "移除<think>...</think>标记及其内容"
            },
            {
                "name": "remove_bracket_think",
                "enabled": False,
                "description": "移除[思考]标记及其内容"
            },
            {
                "name": "remove_internal_monologue",
                "enabled": False,
                "description": "移除内部独白/思考描述，如'好的，用户让我...'"
            },
            {
                "name": "remove_task_description",
                "enabled": False,
                "description": "移除任务描述类思考内容，如'我需要确保回复符合要求'"
            },
            {
                "name": "extract_conversational_response",
                "enabled": False,
                "description": "提取对话式回复，移除非对话性思考内容"
            },
            {
                "name": "extract_final_response",
                "enabled": False,
                "description": "提取最终回复内容，去除前置思考过程"
            },
            {
                "name": "remove_role_prefix",
                "enabled": True,
                "description": "移除回复中重复的角色名前缀，如'兔兔：'、'兔兔:'等"
            }
        ]
    }
}


def get_prompt(prompt_type, **kwargs):
    """
    获取指定类型的prompt
    
    参数:
        prompt_type: prompt类型（default, agent_role, welcome_message）
        **kwargs: 模板参数
    
    返回:
        填充后的prompt文本
    """
    if prompt_type not in PROM_CONFIG:
        raise ValueError(f"未知的prompt类型: {prompt_type}")
    
    config = PROM_CONFIG[prompt_type]
    
    if "system" in config and config.get("enabled", True):
        return config["system"].format(**kwargs)
    
    return ""


def get_system_prompt(agent_description=None):
    """
    获取系统prompt
    
    参数:
        agent_description: 智能体描述（可选）
    
    返回:
        系统prompt文本
    """
    if agent_description:
        return get_prompt("agent_role", agent_description=agent_description)
    return get_prompt("default")


def get_welcome_prompt(agent_description):
    """
    获取欢迎语生成prompt
    
    参数:
        agent_description: 智能体描述
    
    返回:
        欢迎语prompt文本
    """
    return get_prompt("welcome_message", agent_description=agent_description)


def process_user_message(message):
    """
    处理用户消息，应用配置的预处理规则
    
    参数:
        message: 用户原始消息
    
    返回:
        处理后的消息
    """
    if not message:
        return message
    
    config = PROM_CONFIG.get("message_processing", {})
    
    if not config.get("enabled", True):
        return message
    
    processed = message
    
    rules = config.get("rules", [])
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        
        rule_name = rule.get("name")
        
        if rule_name == "strip_whitespace":
            processed = processed.strip()
        
        elif rule_name == "add_no_think":
            suffix = rule.get("suffix", "/no_think")
            if not processed.endswith(suffix):
                processed = processed + suffix
        
        elif rule_name == "add_prefix":
            prefix = rule.get("prefix", "")
            if prefix and not processed.startswith(prefix):
                processed = prefix + processed
        
        elif rule_name == "truncate":
            max_length = rule.get("max_length", 500)
            if len(processed) > max_length:
                processed = processed[:max_length]
        
        elif rule_name == "remove_special_chars":
            import re
            pattern = rule.get("pattern", r"[^\w\u4e00-\u9fff\s。，！？、；：""''（）《》【】]")
            processed = re.sub(pattern, "", processed)
    
    return processed


def add_message_processing_rule(rule):
    """
    添加新的消息预处理规则
    
    参数:
        rule: 规则字典，包含name、enabled、description等字段
    
    返回:
        是否添加成功
    """
    if "name" not in rule:
        raise ValueError("规则必须包含name字段")
    
    config = PROM_CONFIG.get("message_processing", {})
    rules = config.get("rules", [])
    
    for existing_rule in rules:
        if existing_rule.get("name") == rule["name"]:
            raise ValueError(f"已存在名为'{rule['name']}'的规则")
    
    rules.append(rule)
    return True


def update_message_processing_rule(name, updates):
    """
    更新消息预处理规则
    
    参数:
        name: 规则名称
        updates: 更新的字段字典
    
    返回:
        是否更新成功
    """
    config = PROM_CONFIG.get("message_processing", {})
    rules = config.get("rules", [])
    
    for rule in rules:
        if rule.get("name") == name:
            rule.update(updates)
            return True
    
    return False


def remove_message_processing_rule(name):
    """
    删除消息预处理规则
    
    参数:
        name: 规则名称
    
    返回:
        是否删除成功
    """
    config = PROM_CONFIG.get("message_processing", {})
    rules = config.get("rules", [])
    
    for i, rule in enumerate(rules):
        if rule.get("name") == name:
            del rules[i]
            return True
    
    return False


def process_response(response):
    """
    处理模型回复，去除思考内容
    
    参数:
        response: 模型原始回复
    
    返回:
        处理后的回复
    """
    if not response:
        return response
    
    config = PROM_CONFIG.get("response_processing", {})
    
    if not config.get("enabled", True):
        return response
    
    processed = response
    
    rules = config.get("rules", [])
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        
        rule_name = rule.get("name")
        
        if rule_name == "remove_think_tags":
            import re
            processed = re.sub(r'<think>.*?</think>', '', processed, flags=re.DOTALL)
        
        elif rule_name == "remove_bracket_think":
            import re
            processed = re.sub(r'\[思考\].*?(?=[。！？\n]|$)', '', processed, flags=re.DOTALL)
        
        elif rule_name == "remove_internal_monologue":
            import re
            processed = re.sub(
                r'(好的|好的，|嗯，|我想想|让我想想|我需要|首先，|首先我需要|用户让我).*?(?=回复:|回答:|答:|：|。|！|？|\n)',
                '',
                processed,
                flags=re.DOTALL
            )
        
        elif rule_name == "extract_final_response":
            import re
            patterns = [
                r'回复[:：]\s*(.*)$',
                r'回答[:：]\s*(.*)$',
                r'答[:：]\s*(.*)$',
                r'最终回复[:：]\s*(.*)$',
                r'总结[:：]\s*(.*)$'
            ]
            extracted = None
            for pattern in patterns:
                match = re.search(pattern, processed, re.DOTALL)
                if match:
                    extracted = match.group(1).strip()
                    break
            
            if extracted:
                processed = extracted
        
        elif rule_name == "remove_task_description":
            import re
            think_patterns = [
                r'(好的|好的，|嗯，|我想想|让我想想|我需要|首先，|首先我需要|用户让我|用户要求|根据要求).*?(?=好的，|那么，|那就|现在|因此|于是|所以|我来|我会|我将|我可以|我应该|让我|那我|这样|这样的话|就|便|\n\n|\n)',
                r'(我需要确保|我必须保证|我要做到|我应该).*?(?=。|！|？|\n)',
                r'(符合要求|满足条件|达到标准|遵循规则).*?(?=。|！|？|\n)'
            ]
            for pattern in think_patterns:
                processed = re.sub(pattern, '', processed, flags=re.DOTALL)
        
        elif rule_name == "extract_conversational_response":
            import re
            sentences = re.split(r'(。|！|？|\n\n)', processed)
            
            final_sentences = []
            skip_until = None
            
            for i, part in enumerate(sentences):
                if skip_until and part in skip_until:
                    skip_until = None
                    continue
                if skip_until:
                    continue
                
                if any(keyword in part for keyword in ['好的', '我想想', '让我想想', '我需要', '首先', '用户让我', '根据要求']):
                    if i + 1 < len(sentences):
                        next_part = sentences[i + 1]
                        if next_part in ['。', '！', '？']:
                            skip_until = ['。', '！', '？', '\n\n']
                        elif next_part == '\n\n':
                            skip_until = ['\n\n']
                    continue
                
                final_sentences.append(part)
            
            processed = ''.join(final_sentences)
        
        elif rule_name == "remove_role_prefix":
            import re
            while re.match(r'^[\u4e00-\u9fa5\w]{1,8}[：:]\s*', processed):
                processed = re.sub(r'^[\u4e00-\u9fa5\w]{1,8}[：:]\s*', '', processed)
            processed = re.sub(r'\n[\u4e00-\u9fa5\w]{1,8}[：:]\s*', '\n', processed)
    
    processed = processed.strip()
    
    return processed