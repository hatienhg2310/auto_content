import os
import pathlib
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Quản lý các system prompt chuyên biệt cho việc tạo nội dung YouTube
    """
    
    def __init__(self):
        # Đường dẫn đến thư mục system_prompt
        self.root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
        self.system_prompt_dir = os.path.join(self.root_dir, "system_prompt")
        
        # Cache các prompt đã load
        self._prompt_cache: Dict[str, str] = {}
        self._load_system_prompts()
    
    def _load_system_prompts(self):
        """Load tất cả system prompts từ file"""
        try:
            # Load Title and Thumbnail Generator
            title_file = "SYSTEM PROMPT 1 TITLE and NAME THUMB GENERATOR.txt"
            title_path = os.path.join(self.system_prompt_dir, title_file)
            if os.path.exists(title_path):
                with open(title_path, 'r', encoding='utf-8') as f:
                    self._prompt_cache['title_generator'] = f.read()
            
            # Load Description Generator
            desc_file = "SYSTEM PROMPT2 DESCRIPTION GENERTOR.txt"
            desc_path = os.path.join(self.system_prompt_dir, desc_file)
            if os.path.exists(desc_path):
                with open(desc_path, 'r', encoding='utf-8') as f:
                    self._prompt_cache['description_generator'] = f.read()
            
            # Load Tags Generator (từ SYSTEM PROMPT3)
            tags_file = "SYSTEM PROMPT3 TAGS GENERATOR.txt"
            tags_path = os.path.join(self.system_prompt_dir, tags_file)
            if os.path.exists(tags_path):
                with open(tags_path, 'r', encoding='utf-8') as f:
                    self._prompt_cache['tags_generator'] = f.read()
            
            # Load Midjourney Prompt Generator
            midjourney_file = "SYSTEM PROMPT4 MIDJOURNEY PROMPT GENERATOR.txt"
            midjourney_path = os.path.join(self.system_prompt_dir, midjourney_file)
            if os.path.exists(midjourney_path):
                with open(midjourney_path, 'r', encoding='utf-8') as f:
                    self._prompt_cache['midjourney_generator'] = f.read()
            
            logger.info(f"Đã load {len(self._prompt_cache)} system prompts")
            
        except Exception as e:
            logger.error(f"Lỗi khi load system prompts: {str(e)}")
    
    def get_title_generation_prompt(self, channel_name: str, channel_description: str, 
                                   video_topic: str, image_context: str = "") -> str:
        """
        Tạo prompt cho việc generate title và thumbnail text
        """
        base_prompt = self._prompt_cache.get('title_generator', '')
        
        if not base_prompt:
            # Fallback prompt nếu không load được system prompt
            return f"""
Create an optimized YouTube title and thumbnail text for:
- Channel: {channel_name}
- Description: {channel_description}
- Video Topic: {video_topic}
- Image Context: {image_context}

Return format:
🎯 **OPTIMIZED TITLE:**
[60-70 character title with emoji]
🖼️ **THUMBNAIL TEXT:**
[2-3 words for overlay]
"""
        
        # Thêm thông tin cụ thể vào cuối system prompt
        user_input = f"""
**Input**:
- Channel Name: {channel_name}
- Channel Description: {channel_description}
- Video Topic: {video_topic}
- Video Image: {image_context or 'No image provided'}

Analyze the input and respond with the optimized title and thumbnail text following the format specified in the system prompt above.
"""
        
        return base_prompt + "\n\n" + user_input
    
    def get_description_generation_prompt(self, title: str, channel_context: str = "") -> str:
        """
        Tạo prompt cho việc generate description
        """
        base_prompt = self._prompt_cache.get('description_generator', '')
        
        if not base_prompt:
            # Fallback prompt
            return f"""
Create a comprehensive YouTube description for the video titled: "{title}"
Channel context: {channel_context}

Requirements:
- SEO optimized
- Engaging hook in first 125 characters
- Include relevant hashtags
- Professional structure
"""
        
        user_input = f"""
Video Title: {title}
Channel Context: {channel_context}

Generate a complete YouTube description following the flexible framework specified above.
"""
        
        return base_prompt + "\n\n" + user_input
    
    def get_tags_generation_prompt(self, title: str, description: str, channel_context: str = "") -> str:
        """
        Tạo prompt cho việc generate tags - sử dụng system prompt chuyên biệt
        """
        # Sử dụng system prompt chuyên biệt cho tags generation
        system_prompt = self._prompt_cache.get('tags_generator', '')
        
        if not system_prompt:
            # Fallback prompt nếu không load được system prompt
            return f"""
Create 10-15 optimized YouTube tags for:
Title: {title}
Description: {description[:500]}...
Channel Context: {channel_context}

Requirements:
- No punctuation marks (periods, commas, etc.)
- Mix of primary, secondary, and long-tail keywords
- Avoid repetitive patterns
- Each tag should be searchable and relevant

Return tags in JSON format:
{{"tags": ["tag1", "tag2", "tag3", ...]}}
"""
        
        # Tạo user prompt với thông tin cụ thể
        user_prompt = f"""
**Video Information:**
- Title: {title}
- Description: {description[:500]}...
- Channel Context: {channel_context}

**Analysis Required:**
- Extract main keywords from title
- Identify content category and target audience  
- Apply YouTube algorithm optimization
- Ensure tag diversity and avoid repetition

Generate optimized YouTube tags following the system prompt guidelines.
"""
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    def get_midjourney_generation_prompt(self, title: str, keywords: List[str]) -> str:
        """
        Tạo prompt cho việc generate Midjourney prompts
        """
        base_prompt = self._prompt_cache.get('midjourney_generator', '')
        
        if not base_prompt:
            # Fallback prompt
            return f"""
Create 3 Midjourney prompts for YouTube thumbnail based on:
Title: {title}
Keywords: {keywords}

Each prompt should be cinematic, 16:9 aspect ratio, with negative space for text overlay.
"""
        
        user_input = f"""
VIDEO_TITLE: {title}
KEYWORDS: {keywords}

Generate 3 separate Midjourney prompts following the ThumbnailCraft-Pro system specifications above.
"""
        
        return base_prompt + "\n\n" + user_input
    
    def get_integrated_content_prompt(self, channel_name: str, channel_description: str, 
                                    video_topic: str, additional_context: str = "") -> str:
        """
        Tạo prompt tích hợp để generate tất cả nội dung cùng lúc
        """
        return f"""
You are an expert YouTube content creator. Using the best practices from professional YouTube SEO and content creation, generate comprehensive content for a YouTube video.

**Channel Information:**
- Channel Name: {channel_name}
- Channel Description: {channel_description}
- Content Style: Professional, engaging, SEO-optimized

**Video Topic:** {video_topic}

**Additional Context:** {additional_context}

**Requirements:**
Generate a complete content package including:

1. **TITLE** (60-70 characters):
   - SEO optimized with primary keyword first
   - Emotionally engaging with power words
   - Clickable but not misleading
   - Include emoji if appropriate

2. **DESCRIPTION** (800-1500 characters):
   - Hook within first 125 characters
   - Detailed but scannable content
   - Include call-to-action
   - SEO keyword integration
   - Professional formatting with line breaks

3. **TAGS** (10-15 tags):
   - Mix of broad and specific keywords
   - Include channel-relevant tags
   - Target trending topics when relevant

4. **THUMBNAIL_TEXT** (2-3 words):
   - High-impact overlay text
   - Readable and attention-grabbing
   - Complementary to title

5. **IMAGE_PROMPTS** (3 prompts):
   - Detailed prompts for AI image generation
   - Include technical specifications
   - Optimized for YouTube thumbnail format
   - Consider mood and visual appeal

**Output Format (JSON):**
```json
{{
    "title": "Your optimized title here",
    "description": "Your complete description here",
    "tags": ["tag1", "tag2", "tag3", ...],
    "thumbnail_text": "POWER WORDS",
    "image_prompts": [
        "Detailed prompt 1 for main image",
        "Detailed prompt 2 for alternative image", 
        "Detailed prompt 3 for thumbnail"
    ]
}}
```

Focus on creating content that perfectly matches the channel's niche and audience expectations while maximizing discoverability and engagement.
"""

# Singleton instance
prompt_manager = PromptManager() 