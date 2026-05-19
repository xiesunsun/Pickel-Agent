---
name: image-generator
description: Use when users need help turning an idea into a high-quality image generation prompt, or when they want to directly generate an image. Covers photography, illustration, 3D render, concept art, anime, product shots, landscapes, characters, logos, and other visual content across any subject and style.
---

# Image Generator

通用图片生成 skill：负责把用户的模糊想法结构化拆解，产出可直接投喂扩散模型 / Gemini image 模型的高质量 prompt，并在用户要求时落地成图片文件。

## 触发范围

- 用户给了一个主题、情绪或场景，希望拿到完整图片 prompt
- 用户想生成写实照片、插画、3D 渲染、概念艺术、动漫、海报、产品图、logo、图标、场景图、角色设定等任意视觉内容
- 用户希望画面更有风格感、更精致、更"可控"
- 用户需要结构化分析、风格引导、负面提示词
- 用户明确要求"帮我出一张图 / 画一张 / 生成一张图"——这种情况除了产出 prompt 还要真正调用脚本

## 默认边界

- 不主动往露骨色情、真实人物肖像（名人）、仇恨、暴力猎奇方向发挥
- 涉及人物时，如果年龄不明确，默认写成 adult / young adult；不做未成年性化
- 风格、媒介、主体全部按用户意图来，不强塞某一种美学
- 用户没说的参数，主动用能显著提升画面的合理默认值补齐（光线、镜头、构图、材质、细节级别）

## 执行顺序

1. 判断用户要的是 **"只要 prompt"** 还是 **"直接出图"**
2. 用下面的分析框架做结构化拆解
3. 参考 few-shot 组织思路，但不复制字面内容
4. 产出三段结果：`Analysis` / `Prompt` / `Negative Prompt`
5. 只有用户明确要落地图像时，才调用脚本生成图片
6. 调用脚本时使用绝对路径，不要改写成相对路径

## 分析框架

每次先按这些通用维度分析，再合成最终 prompt：

- `medium`
  媒介/技术：photography、digital illustration、oil painting、watercolor、3D render (Octane / Blender)、anime cel shading、pixel art、vector、concept art、isometric、line art 等
- `style_family`
  具体风格取向：cinematic、studio portrait、Studio Ghibli、cyberpunk、minimalist flat、80s retro、ukiyo-e、low-poly、ink wash 等
- `subject`
  主体是谁/什么：人物、动物、物品、建筑、自然景观、抽象图形，以及主体的关键特征
- `subject_details`
  主体的外观、姿态、材质、表情、状态、数量（人数、个数）
- `setting`
  环境/背景：室内、室外、虚构场景、纯背景色、棚拍、抽象空间
- `composition`
  构图：景别（特写/中景/广角）、机位、视角、规则（三分法、居中、对角）、留白
- `lighting`
  光线：自然光、黄金时刻、逆光、棚拍柔光、霓虹、戏剧性硬光、体积光、环境光等
- `color_palette`
  色彩：主色调、色温、饱和度、对比度、是否限定调色板
- `mood`
  情绪/氛围：宁静、紧张、梦幻、孤独、浪漫、史诗感、俏皮等
- `camera_or_render`
  摄影/渲染参数：镜头焦段、景深、快门、胶片；或渲染引擎、材质、光追、采样
- `detail_and_finish`
  细节级别与完成度：ultra-detailed、hyperrealistic、clean vector、painterly、sketchy、film grain、8K、magazine finish
- `negative_controls`
  需要回避的问题：解剖错误、手指异常、水印文字、低分辨率、脏背景、风格漂移、额外肢体等

> 根据任务性质，允许略过不相关维度（比如抽象图形不需要 `camera_or_render`）。

## Few-Shot

用这些示例引导自己的思考方式，**不要机械复制字面内容**，也不要把所有 prompt 都写成同一种语气。

### 示例 1: 写实人像摄影

**User intent**
想要一张自然光下的窗边人像，安静、有电影感。

**Analysis**
- `medium`: photography
- `style_family`: cinematic natural-light portrait
- `subject`: adult person sitting by a window
- `subject_details`: relaxed posture, soft gaze toward the window, casual knit sweater
- `setting`: quiet apartment interior in the late afternoon
- `lighting`: warm directional window light, soft falloff into shadow
- `color_palette`: muted warm tones, amber and soft brown
- `mood`: calm, contemplative, intimate
- `camera_or_render`: 50mm lens, shallow depth of field, f/1.8, 35mm film look
- `detail_and_finish`: fine skin texture, subtle film grain, editorial finish
- `negative_controls`: harsh flash, plastic skin, warped hands

**Prompt**
A cinematic natural-light portrait of an adult person sitting by a window in a quiet apartment in the late afternoon, relaxed posture, soft gaze turned toward the light, casual knit sweater, warm directional window light with gentle falloff into shadow, muted amber and soft brown palette, calm contemplative mood, shot on 50mm at f/1.8, shallow depth of field, subtle 35mm film grain, fine skin texture, editorial finish, high detail

**Negative Prompt**
harsh on-camera flash, plastic over-smoothed skin, warped hands, extra fingers, distorted facial features, cluttered background, low resolution, text, watermark

### 示例 2: 自然风光摄影

**User intent**
想要一张冰岛风感觉的黑沙滩日出风景图。

**Analysis**
- `medium`: landscape photography
- `style_family`: epic nature / travel editorial
- `subject`: black sand beach with basalt sea stacks
- `subject_details`: crashing waves, wet reflective sand, distant sea stacks
- `setting`: remote Nordic coastline at sunrise
- `lighting`: low golden sunrise light breaking through moody clouds
- `color_palette`: cold blues and charcoal with warm golden highlights
- `mood`: vast, serene, slightly dramatic
- `camera_or_render`: 16-35mm wide angle, f/11, long exposure for silky waves, tripod
- `detail_and_finish`: sharp foreground-to-infinity detail, National Geographic polish
- `negative_controls`: tourists, power lines, overcooked HDR

**Prompt**
An epic landscape photograph of a remote Nordic black sand beach at sunrise, basalt sea stacks rising from crashing waves, wet reflective sand in the foreground, low golden sunrise light breaking through moody layered clouds, cold blue and charcoal tones contrasted with warm golden highlights, vast serene slightly dramatic mood, shot on 16-35mm wide angle at f/11 with a long exposure giving the water a silky texture, sharp detail from foreground to horizon, National Geographic travel editorial finish, ultra high resolution

**Negative Prompt**
tourists, footprints, power lines, buildings, oversaturated HDR, fake-looking sky, blurry foreground, lens flare artifacts, text, watermark

### 示例 3: 产品 / 商业静物

**User intent**
要一张极简风的香水瓶产品图，用于电商首图。

**Analysis**
- `medium`: commercial product photography
- `style_family`: minimalist luxury e-commerce
- `subject`: a clear glass perfume bottle with a gold cap
- `subject_details`: faceted crystal-like body, subtle amber liquid inside, clean label
- `setting`: seamless studio backdrop with a soft stone pedestal
- `lighting`: large softbox key from upper-left, subtle rim light from the right, controlled specular highlights on glass edges
- `color_palette`: warm beige background, gold and amber accents
- `mood`: refined, premium, quiet luxury
- `camera_or_render`: 100mm macro, f/8, tack-sharp focus on the bottle
- `detail_and_finish`: crisp glass refraction, clean retouching, advertising-grade polish
- `negative_controls`: cluttered props, visible fingerprints, distracting reflections, busy background

**Prompt**
A minimalist luxury e-commerce product photograph of a clear faceted glass perfume bottle with a gold cap and subtle amber liquid inside, placed on a soft stone pedestal against a seamless warm beige studio backdrop, large softbox key light from the upper left, subtle rim light from the right, controlled specular highlights along the glass edges, refined quiet-luxury mood, shot on 100mm macro at f/8 with tack-sharp focus, crisp glass refraction, clean advertising-grade retouching, high detail

**Negative Prompt**
cluttered props, visible fingerprints, messy reflections, busy background, oversaturated colors, blurry label, text artifacts, watermark, low resolution

### 示例 4: 插画 / 动漫风

**User intent**
想要吉卜力风格的小女孩和猫在乡间小径的插画。

**Analysis**
- `medium`: hand-painted 2D illustration
- `style_family`: Studio Ghibli inspired, soft anime watercolor
- `subject`: a young girl walking with a small tabby cat
- `subject_details`: summer dress, straw hat, cat trotting beside her, both looking ahead with gentle curiosity
- `setting`: countryside path lined with tall summer grass and wildflowers, distant rolling hills
- `lighting`: soft late-afternoon sunlight, golden warm backlight
- `color_palette`: lush greens, warm yellows, pastel blue sky
- `mood`: peaceful, nostalgic, whimsical
- `camera_or_render`: wide medium shot, slight low angle so grass frames the foreground
- `detail_and_finish`: hand-painted backgrounds, delicate line work, painterly brush texture
- `negative_controls`: harsh digital lines, 3D look, photorealism, dark gritty palette

**Prompt**
A hand-painted Studio Ghibli inspired illustration of a young girl in a summer dress and straw hat walking along a countryside path with a small tabby cat trotting beside her, tall summer grass and wildflowers framing the foreground, distant rolling hills, soft late-afternoon golden backlight, lush green and warm yellow palette with a pastel blue sky, peaceful nostalgic whimsical mood, wide medium shot from a slight low angle, painterly brush texture, delicate line work, hand-painted background, anime watercolor finish

**Negative Prompt**
photorealism, 3D render, harsh digital outlines, dark gritty palette, horror elements, distorted anatomy, extra limbs, text, watermark

### 示例 5: 科幻概念艺术

**User intent**
想要一张未来废墟之城的概念图，配一个孤独旅者。

**Analysis**
- `medium`: digital concept art
- `style_family`: sci-fi matte painting, cinematic key frame
- `subject`: a lone traveler silhouetted on a ridge overlooking a ruined future city
- `subject_details`: weathered long coat, backpack, staff, scale kept small against the environment
- `setting`: overgrown megacity ruins reclaimed by nature, broken skyscrapers and hovering derelict structures
- `lighting`: diffuse dawn light with volumetric god rays filtering through dust and mist
- `color_palette`: muted teal and ochre, hint of warm amber from distant fires
- `mood`: melancholic, awe-inspiring, quietly hopeful
- `camera_or_render`: ultrawide cinematic framing, strong atmospheric perspective, depth layering
- `detail_and_finish`: matte painting polish, painterly detail, Blade Runner / Horizon Zero Dawn reference energy
- `negative_controls`: cartoonish style, cluttered foreground, modern logos, text

**Prompt**
A cinematic sci-fi matte painting concept art of a lone traveler in a weathered long coat with a backpack and staff, silhouetted on a ridge overlooking a ruined future megacity reclaimed by nature, broken skyscrapers and derelict hovering structures partially swallowed by overgrown vegetation, diffuse dawn light with volumetric god rays cutting through dust and mist, muted teal and ochre palette with a hint of warm amber from distant fires, melancholic awe-inspiring yet quietly hopeful mood, ultrawide cinematic framing with strong atmospheric perspective and clear depth layering, matte painting polish, painterly brush detail, key frame illustration finish, ultra high detail

**Negative Prompt**
cartoonish style, chibi proportions, cluttered foreground, modern brand logos, readable text, low-poly look, flat lighting, oversaturated neon clichés, watermark

## 合成规则

生成最终 `Prompt` 时遵循：

- 写作顺序：**媒介/风格 → 主体 → 主体细节 → 场景 → 光线 → 色彩 → 情绪 → 镜头/渲染 → 细节与完成度**
- 用具体视觉语言，少用空泛形容词（不要只写 "beautiful / amazing / stunning"）
- 风格锚点要明确：要么写媒介（photograph / illustration / 3D render），要么写参考美学（Ghibli / cyberpunk / matte painting），避免风格漂移
- 人物图主动写明 adult / young adult 等年龄范围，避免歧义
- 用户没说的参数，补齐合理默认值而不是留空：构图、光线、色彩、细节级别至少挑两项补上
- Prompt 是**一整段连贯文字**（逗号分隔短语），不要写成分点列表
- Negative Prompt 针对这一类图的常见失败模式来写，而不是套一份万能模板

## 默认输出格式

```text
Analysis
- medium: ...
- style_family: ...
- subject: ...
- subject_details: ...
- setting: ...
- composition: ...
- lighting: ...
- color_palette: ...
- mood: ...
- camera_or_render: ...
- detail_and_finish: ...
- negative_controls: ...

Prompt
<一整段可直接投喂模型的完整提示词>

Negative Prompt
<一整段负面提示词>
```

（不相关的维度可以省略或写 `n/a`。）

## 生成图片

当用户明确要求直接出图时，执行：

```bash
uv run python /Users/ssunxie/code/myopenclaw/.agent/skills/image-generator/scripts/generate_image.py \
  --prompt "<prompt>" \
  --output "<output_path>"
```

默认值：

- model: `gemini-3.1-flash-image-preview`
- aspect ratio: `16:9`
- image size: `1K`

仅在用户明确指定或画面性质需要时再传 `--aspect-ratio`、`--image-size`、`--model`。常见选择建议：

- 人像 / 竖版海报：`--aspect-ratio 9:16` 或 `3:4`
- 产品 / 方图：`--aspect-ratio 1:1`
- 风景 / 电影感：`--aspect-ratio 16:9`
- 需要更高精度或大尺寸打印：`--image-size 2K` 或 `4K`
- 复杂构图 / 多主体场景：考虑 `--model gemini-3-pro-image-preview`

## 失败处理

- 缺少 `GEMINI_API_KEY` → 直接说明环境变量未配置
- 缺少 `google-genai` → 直接说明项目依赖未安装
- 模型未返回图像 → 把错误和可用文本原样返回给用户，不要编造

## 参考

- 官方文档：[Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation)
