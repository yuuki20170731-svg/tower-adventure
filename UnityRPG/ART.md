# イラスト制作記録

内蔵 imagegen を使用。既存作品のキャラクターをコピーせず、王道ファンタジーRPGのオリジナル素材として制作しました。

採用素材は Assets/Resources/Art/party_hd.png、enemies_hd.png、props_hd.png、landscape_hd.png。人物6体（プレイ用5人＋旅人）、敵12体、小物8点、背景1点です。アトラスを直接UV参照し、生成された透過を維持しています。旧素材は互換用に残しています。

## 使用したプロンプト

### party

Use case: stylized-concept. Asset: a production-ready TRANSPARENT character atlas for an original Japanese fantasy RPG. Exactly 3 columns by 2 rows, six equally sized cells, no grid lines, no labels, no text, full body characters in each cell, generous transparent gutters and at least 10% margin within each cell, nothing crossing cell boundaries. TOP ROW left to right: young adventurous hero with short chestnut hair, teal tunic, cream cape, leather boots, simple silver sword; broad friendly red-haired warrior in bronze plate with round shield; kind female priest with ivory and blue vestments, staff and short auburn bob. BOTTOM ROW: nimble female elf archer with dark green cloak and brown hair, wooden bow; scholarly young male mage with violet cloak and star-tipped staff; warm older travelling guide in ochre coat carrying a lantern. Contemporary polished console JRPG character illustrations: expressive welcoming faces, heroic but modest proportions, exquisite clean contour linework, lush soft cel shaded painting, appealing rounded silhouettes, coherent warm gold / teal accents, subtle materials and soft directional lighting. All characters standing three-quarter toward viewer, cohesive art direction. Completely original character designs, no franchise characters, no logos, no existing artist imitation. Landscape 3:2 image. Genuine transparent alpha background.

### enemies

Use case: stylized-concept. Asset: transparent enemy atlas for an original Japanese fantasy RPG. Exactly 4 columns by 3 rows with TWELVE separate fully visible creatures centered in equally sized cells. Generous transparent gutters and at least 12% clear margin within every cell. No grid lines, no text, no objects crossing cells. Row 1 left to right: round emerald jelly monster with two leaflike ears and amber eyes; mischievous small purple goblin with brass dagger and red scarf; blue-gray wolf with crystalline mane; friendly-menacing ivory skeleton soldier with rusty shield. Row 2: bulky moss-covered stone golem with glowing teal core; pallid lavender ghoul with ragged cape; armored black knight with gold accents and crimson plume; small female frost sorceress with blue cloak and icy staff. Row 3: burly boar-faced orc with huge wooden club; crimson dragon with gold wing membranes; large majestic bronze-armored tower guardian wielding a hammer; imposing violet celestial dragon with teal luminous runes, final boss. Style: polished contemporary console JRPG monster illustrations, lively readable silhouettes, expressive cartoon faces, elegant bold contours, beautiful soft cel shading, painterly highlights, tasteful material detail, coherent warm-gold and teal art direction. Charming adventure rather than horror. Ground-facing battle poses, three-quarter view. Full bodies and wings inside each cell. Completely original designs, no recognizable franchise monsters, no imitation of a named artist. Landscape 4:3 image. True transparent alpha background.

### props

Use case: stylized-concept. Asset: game environment prop atlas for a beautiful contemporary Japanese fantasy RPG. Exactly 4 columns by 2 rows, EIGHT separate props, each in equal cells with generous transparent gutters, 12% empty margin, no cell overlaps. TOP ROW left to right: ornate closed mahogany treasure chest with brass fittings; ancient carved sandstone door in small arched frame with teal runes; stone spiral staircase descending into a circular opening; idyllic miniature rest camp with cream canvas tent, warm lantern and bedroll. BOTTOM ROW left to right: luminous turquoise healing fountain with stone basin; golden speech-scroll marker with small glowing amber orb; polished golden crossed swords encounter marker; an ornate ancient tower arch with a ruby boss sigil. Top-down three-quarter isometric-ish RPG props, very readable at small size, crisp exquisite contours, painterly soft cel shading, warm stone and teal / amber lighting. Match a polished original fantasy JRPG, illustrative not pixel art or photographic. No letters, no numbers, no logos, no gridlines, no visible background or ground square. Individual props isolated with true transparent alpha. Landscape 2:1 composition.

### landscape

Use case: illustration-story. Asset: high quality widescreen background painting for an original modern Japanese fantasy RPG title and battle screen. A serene ancient circular stone arena with softly weathered pale sandstone paving in the lower half, lush green grass and flowers at the edges, towering broken arches and a majestic spiralling ivory fantasy tower in the distant center background, turquoise sky, drifting clouds, warm afternoon sunshine, soft distant blue mountains. Composition: central lower 60% empty quiet open paving for enemies and UI; rich architectural detail at side edges and distant tower above; horizon around 42% from top. Charming bright grand adventure, polished console JRPG art direction, fine clean contour work, painterly cel-shaded shading, elegant soft depth, warm golden light, emerald / teal color accents, sophisticated colors and readable low-contrast foreground. No characters, no creatures, no text, no logo, no watermark. Completely original world. Wide 16:9 landscape image.

人物アトラスの余白を調整した試作も生成しましたが、採用版は最初の生成です。

## 章別背景

`Assets/Resources/Art/chapters_hd.png` はimagegenで新規制作した1536×1024の背景アトラスです。2列×5行、上から左→右に、忘れられた遺跡、森、衛兵の回廊、記憶の庭、紫の研究所、星の砦、氷水路、機関、竜門、星の深淵。タイトルは以前の背景を使用し、探索と戦闘で章別背景を参照します。人物・敵・文字を含めないオリジナルのファンタジー風景として制作しました。

環境音は外部素材を使わず、章ごとに雑音・鳥のような短い音・水や風・機関の拍動・低い響きをUnity内で合成します。聴感の実地調整は別途必要です。

