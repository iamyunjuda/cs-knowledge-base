# LLM (Large Language Model) — 대규모 언어 모델의 핵심 원리

## 핵심 정리

### LLM이란?

대규모 언어 모델(Large Language Model)은 방대한 텍스트 데이터로 학습된 딥러닝 모델로, 자연어를 이해하고 생성할 수 있다. 핵심은 **다음 토큰 예측**(Next Token Prediction)이다. 주어진 텍스트 시퀀스에서 다음에 올 가능성이 높은 토큰을 확률적으로 예측하는 것이 기본 동작 원리다.

### Transformer 아키텍처

2017년 Google의 "Attention Is All You Need" 논문에서 제안된 Transformer가 현재 모든 LLM의 기반이다.

**기존 RNN/LSTM의 한계:**
- 순차적으로 처리해야 해서 병렬화가 불가능
- 긴 시퀀스에서 앞쪽 정보가 점점 희미해지는 장기 의존성(Long-range Dependency) 문제

**Transformer의 해결 방식:**
- **Self-Attention**: 시퀀스 내 모든 위치를 동시에 참조하여 관련성을 계산. 각 토큰이 다른 모든 토큰과의 관계를 가중치로 학습한다
- **Multi-Head Attention**: 여러 개의 Attention Head가 서로 다른 관점(문법적 관계, 의미적 유사성 등)을 병렬로 학습
- **Positional Encoding**: Self-Attention은 순서 정보가 없으므로, 위치 정보를 별도로 주입

```
입력 → Embedding + Positional Encoding → [Multi-Head Attention → Feed Forward] × N층 → 출력
```

**Encoder-Decoder vs Decoder-Only:**
- 원래 Transformer는 Encoder + Decoder 구조 (번역 등 seq2seq 태스크에 적합)
- GPT 계열은 **Decoder-Only** 구조: 왼쪽→오른쪽으로만 참조하는 Causal Attention으로 텍스트 생성에 특화
- BERT는 **Encoder-Only** 구조: 양방향 참조로 텍스트 이해에 특화

### 토큰화 (Tokenization)

LLM은 문자가 아닌 **토큰** 단위로 처리한다. 토큰은 단어보다 작을 수도 있고, 자주 등장하는 패턴은 하나의 토큰이 될 수도 있다.

- **BPE (Byte Pair Encoding)**: GPT 계열에서 사용. 빈도 높은 바이트 쌍을 반복적으로 병합하여 어휘 구성
- **SentencePiece**: 언어에 독립적인 토크나이저. 공백을 특별 취급하지 않아 한국어/일본어 등에도 적합
- **WordPiece**: BERT에서 사용. BPE와 유사하지만 우도(likelihood) 기반으로 병합

```
"Hello world" → ["Hello", " world"]     (2토큰)
"안녕하세요"    → ["안녕", "하세요"]        (2토큰, 모델에 따라 다름)
"Tokenization" → ["Token", "ization"]   (2토큰)
```

> 토큰 수 ≠ 글자 수 ≠ 단어 수. 영어는 대략 1토큰 ≈ 0.75단어, 한국어는 토큰 효율이 더 낮다 (같은 의미를 표현하는 데 더 많은 토큰 필요).

### 학습 과정

LLM의 학습은 크게 3단계로 나뉜다:

**1단계: Pre-training (사전 학습)**
- 인터넷에서 수집한 수조 개의 토큰으로 비지도 학습
- 목표: 다음 토큰 예측을 통해 언어의 구조, 사실, 추론 능력을 학습
- 수천~수만 GPU로 수개월 소요. 비용은 수천만 달러 규모
- 이 단계에서 모델의 기본 능력(언어 이해, 세계 지식, 추론)이 결정됨

**2단계: Fine-tuning (미세 조정)**
- **SFT (Supervised Fine-Tuning)**: 사람이 작성한 고품질 대화 데이터로 학습하여 "대화형 AI"로 변환
- **Instruction Tuning**: 다양한 형식의 지시사항에 따르도록 학습

**3단계: RLHF (Reinforcement Learning from Human Feedback)**
- 사람의 선호도 데이터로 보상 모델(Reward Model)을 학습
- 보상 모델의 피드백을 기반으로 PPO 등 강화학습 알고리즘으로 모델 최적화
- 이 단계를 통해 유해한 출력 감소, 도움이 되는 응답 생성 등 사람의 의도에 맞게 정렬(Alignment)
- **최신 동향 (2024~2025)**:
  - **DPO (Direct Preference Optimization)**: 보상 모델 없이 선호도 데이터에서 직접 최적화. RLHF보다 구현이 간단하고 안정적이어서 많은 모델이 채택
  - **추론 강화학습**: DeepSeek R1 (2025.01)이 강화학습만으로도 추론(reasoning) 능력을 크게 향상시킬 수 있음을 입증
  - **합성 데이터 활용**: 2024년부터 주요 연구소들이 학습 파이프라인에 AI가 생성한 합성 데이터를 적극 활용

### 추론 시 주요 파라미터

| 파라미터 | 설명 | 일반적인 범위 |
|---------|------|-------------|
| **Temperature** | 확률 분포의 날카로움을 조절. 낮을수록 결정적(greedy), 높을수록 다양한 출력 | 0.0 ~ 2.0 |
| **Top-p (Nucleus Sampling)** | 누적 확률이 p 이상인 토큰 집합에서만 샘플링 | 0.0 ~ 1.0 |
| **Top-k** | 확률 상위 k개 토큰에서만 샘플링 | 1 ~ 100+ |
| **Max Tokens** | 생성할 최대 토큰 수 | 모델마다 다름 |
| **Context Window** | 모델이 한 번에 처리할 수 있는 최대 토큰 수 (입력 + 출력) | 4K ~ 1M+ |

> Temperature 0은 항상 가장 확률 높은 토큰을 선택(deterministic). Temperature가 높으면 낮은 확률의 토큰도 선택될 수 있어 창의적이지만 일관성이 떨어짐.

### GPT 계열 발전 과정

LLM의 규모 변화를 이해하기 위해 GPT 시리즈의 발전을 살펴보면:

| 모델 | 시기 | 파라미터 | 핵심 의의 |
|------|------|----------|-----------|
| GPT-1 | 2018.06 | 1.17억 | 최초의 GPT. Transformer Decoder 기반 사전학습의 가능성 입증 |
| GPT-2 | 2019.02 | 15억 | 10배 스케일업. 제로샷 텍스트 생성 능력 입증 |
| GPT-3 | 2020.05 | 1,750억 | 117배 스케일업. Few-shot 학습 능력의 비약적 발전. 프롬프트 엔지니어링의 시작 |
| GPT-3.5 | 2022.11 | — | ChatGPT의 기반. RLHF 적용으로 대화형 AI 대중화의 계기 |
| GPT-4 | 2023.03 | ~1.76조 (추정, MoE) | 멀티모달(텍스트+이미지). 추론 능력 대폭 향상 |
| GPT-4o | 2024.05 | — | Omni 모델. 텍스트/이미지/음성 네이티브 통합 |

> GPT-1에서 GPT-3까지 파라미터가 1,495배 증가했다. 그러나 GPT-4부터는 단순 파라미터 증가보다 MoE(Mixture of Experts) 아키텍처, 학습 데이터 품질, RLHF 등 방법론 혁신이 더 중요해졌다.

### 주요 모델 비교 (2025~2026년 기준)

| 모델 | 개발사 | 컨텍스트 윈도우 | 특징 |
|------|-------|----------------|------|
| **GPT-4o** | OpenAI | 128K | 멀티모달(텍스트/이미지/음성), 빠른 응답 |
| **Claude (Opus/Sonnet)** | Anthropic | 200K (베타 1M) | Constitutional AI 기반 안전성, 코딩/다단계 추론 강점 |
| **Gemini 2.5 Pro** | Google | 1M | 멀티모달 네이티브, Google 서비스 통합, 코딩/빠른 추론 |
| **Llama 4 Scout** | Meta | 10M | 오픈소스, MoE(17B 활성/109B 총), 초대형 컨텍스트 |
| **Mistral** | Mistral AI | 128K | 오픈소스, 경량 모델 대비 높은 성능 |

**모델별 설계 철학의 차이**:
- **OpenAI GPT**: 범용 성능 극대화. o1/o3 등 추론 특화 모델 별도 라인업
- **Anthropic Claude**: Constitutional AI로 안전성과 도움 됨의 균형. Haiku(경량) → Sonnet(균형) → Opus(최고 성능) 3단계 라인업
- **Meta Llama**: 오픈소스/오픈웨이트로 생태계 확장. 수많은 파생 모델(Vicuna, Alpaca 등)의 기반
- **Google Gemini**: 처음부터 멀티모달로 설계. Google 인프라와 통합

### 실용적 고려사항

**RAG (Retrieval-Augmented Generation):**
- LLM의 지식 한계(학습 데이터 시점까지만 알고 있음)를 보완하는 기법. "오픈 북 시험"처럼 답변 전에 관련 문서를 먼저 읽는 방식
- **RAG 파이프라인**:
  1. **Ingestion**: 문서를 청크로 분할 → 임베딩 벡터로 변환 → 벡터 DB에 저장
  2. **Retrieval**: 사용자 질문을 임베딩 → 벡터 DB에서 유사도 기반 검색
  3. **Augmentation**: 검색된 문서 + 사용자 질문을 하나의 프롬프트로 결합
  4. **Generation**: LLM이 증강된 프롬프트를 기반으로 답변 생성
- **장점**: Hallucination 감소, 최신 정보 반영, 조직 내부 데이터 활용, 출처 추적 가능
- **2025년 동향**: Graph RAG(지식 그래프 기반 검색), Agentic RAG(에이전트가 검색 전략을 동적으로 결정), 멀티모달 검색으로 진화 중

**프롬프트 엔지니어링:**
- **Zero-shot**: 예시 없이 바로 지시. 잘 알려진 단순 작업에서 효과적
- **Few-shot**: 몇 가지 (입력, 출력) 예시를 포함하여 원하는 형식/패턴 유도. 복잡하거나 특수한 형식이 필요한 작업에서 유용
- **Chain-of-Thought (CoT)**: "단계별로 생각해보세요" 등의 지시로 중간 추론 과정을 명시적으로 유도. 수학/논리 문제에서 정확도 대폭 향상 (Wei et al., 2022)
- **Self-Consistency**: 여러 추론 경로를 생성한 뒤 가장 일관된 답을 선택
- **Tree-of-Thought (ToT)**: 트리 구조로 여러 해결 경로를 탐색, 필요 시 백트래킹
- **System Prompt / 역할 부여**: 모델의 역할, 제약조건, 출력 형식을 사전에 정의

## 헷갈렸던 포인트

### Q: LLM은 정말로 "이해"하는 건가? 기존 NLP와 뭐가 다른 건가?

**전통 NLP (2017년 이전 주류)**:
- 규칙 기반(정규식, 문법 규칙) 또는 통계적 모델(TF-IDF, 나이브 베이즈)
- RNN/LSTM은 순차 처리로 병렬화 어렵고 긴 문맥 처리에 한계
- 특정 태스크에 특화된 모델을 따로 만들어야 함 (감성 분석, 번역, 요약 모델 각각 별도)
- 비교적 적은 데이터와 컴퓨팅 자원으로 학습 가능

**LLM**:
- Transformer 기반 딥러닝으로 언어의 복잡한 패턴을 학습
- **하나의 모델**로 번역, 요약, QA, 코드 생성 등 다양한 작업 수행 (General-Purpose)
- 대규모 데이터(수백 TB)와 GPU/TPU 클러스터 필요
- Fine-tuning이나 프롬프트 엔지니어링만으로 새 작업에 적용 가능

**왜 헷갈리기 쉬운가**: NLP는 "분야"이고, LLM은 그 분야의 "도구/방법론"이다. LLM도 NLP의 일부이지만, 이전 NLP 접근법과 패러다임이 근본적으로 달라 별개처럼 느껴진다.

"이해"에 대해서는 논란이 있다. LLM은 통계적 패턴 매칭을 극도로 잘 수행하는 것이지, 사람처럼 의미를 "이해"하는 것은 아니라는 관점(Chinese Room Argument)이 있는 반면, 충분히 큰 규모의 패턴 매칭이 실질적 이해와 구분할 수 없다는 관점도 있다. 중요한 것은 **실용적으로 유용한 출력을 생성할 수 있다는 사실**이다.

### Q: Hallucination(환각)은 왜 발생하는가?

LLM은 확률적으로 "그럴듯한" 다음 토큰을 예측하는 모델이다. 학습 데이터에 없거나 모호한 정보에 대해서도, 문맥상 자연스러운 텍스트를 생성하려는 경향이 있어 **사실이 아닌 내용을 마치 사실인 것처럼** 출력한다.

원인:
1. **학습 목표의 본질**: LLM은 "사실을 말하라"가 아니라 "다음에 올 가능성 높은 토큰을 예측하라"로 학습된다. 통계적으로 그럴듯한 패턴을 따르는 것이지, 사실 여부를 검증하는 것이 아니다
2. **학습/평가 인센티브 문제**: OpenAI의 2025년 9월 논문에 따르면, 표준 학습 및 평가 절차가 불확실할 때 "모르겠다"고 하는 것보다 **자신 있게 추측하는 것**에 보상을 준다
3. **이론적 한계**: 학습 이론 관점에서 LLM은 모든 계산 가능한 함수를 학습할 수 없으므로, 범용 문제 해결기로 사용될 경우 할루시네이션은 불가피하다 (Xu et al., 2024, "Hallucination is Inevitable")
4. **내부 메커니즘**: Anthropic의 해석 가능성 연구에서, 모델 내부에 "모르면 답하지 않는" 억제 회로가 존재하지만, 이 억제가 불완전하게 작동할 때 할루시네이션이 발생함을 발견
5. **Knowledge Cutoff**: 학습 시점 이후의 정보는 모름. 그런데도 자연스럽게 답변하려 함
6. **Compression Artifact**: 수조 토큰의 지식을 유한한 파라미터에 압축하면서 발생하는 손실

> 2025년 현재 학계의 주류 인식은 "할루시네이션을 완전히 제거하는 것은 불가능하므로, 불확실성을 관리하는 방향으로 접근해야 한다"는 것이다.

해결 방향: RAG, 외부 도구 연동(Calculator, Search), Fine-tuning, Temperature 낮추기, 구조화된 프롬프트

### Q: "창발적 능력(Emergent Abilities)"이란?

작은 모델에서는 나타나지 않다가, 모델 규모(파라미터 수, 학습 데이터)가 일정 임계점을 넘으면 갑자기 나타나는 능력을 말한다 (Wei et al., 2022). 예를 들어 산술 추론, 다단계 논리 추론, 코드 생성 등이 있다.

**논쟁이 존재한다:**
- **찬성 측**: 규모가 커지면서 질적으로 새로운 능력이 갑자기 출현한다
- **반대 측**: 진정한 "창발"이 아니라, 인컨텍스트 학습 + 모델 메모리 + 언어 지식의 조합이 특정 평가 지표에서 비선형적으로 드러나는 것일 뿐이다
- **2025년 관점**: OpenAI o1/o3 등 추론 특화 모델의 등장으로 "규모만 키우면 되는가"에서 "학습 방법론(특히 강화학습)도 핵심이다"로 논의가 이동. o1은 Competition Math(AIME 2024)에서 83.3%를 달성하여 GPT-4o의 13.4%를 크게 상회

### Q: Context Window가 크면 무조건 좋은 건가?

꼭 그렇지는 않다.

- **"Lost in the Middle" 현상**: 컨텍스트가 길어지면 중간에 있는 정보를 제대로 활용하지 못하는 경향이 관찰됨
- **비용**: 토큰 수에 비례하여 API 비용 증가
- **속도**: Self-Attention의 계산 복잡도가 O(n²)이므로 컨텍스트가 길면 처리 시간 증가
- **품질**: 관련 있는 정보만 선별하여 제공하는 것이 긴 컨텍스트에 무작정 모든 정보를 넣는 것보다 나은 경우가 많음

### Q: Temperature와 Top-p를 동시에 쓰면 어떻게 되는가?

둘 다 토큰 선택의 다양성을 조절하는 파라미터인데, **동시에 적용된다**. 보통은 하나만 조절하고 다른 하나는 기본값으로 두는 것이 권장된다.

- 코드 생성, 사실 기반 답변: `temperature=0` (Top-p 무관)
- 창의적 글쓰기: `temperature=0.7~1.0`, `top_p=0.9~0.95`
- 브레인스토밍: `temperature=1.0+`, `top_p=0.95~1.0`

### Q: 파라미터 수가 크면 무조건 성능이 좋은가?

반드시 그렇지는 않다. **Scaling Law**(Chinchilla 논문, 2022)에 의하면 모델 크기와 학습 데이터 양의 균형이 중요하다. 파라미터 수만 크고 데이터가 부족하면 비효율적이다.

- Llama 3 8B는 특정 벤치마크에서 이전 세대 70B 모델과 비슷한 성능
- 학습 데이터의 질, 학습 기법(SFT, RLHF), 아키텍처 최적화가 모두 영향을 줌
- **MoE (Mixture of Experts)**: Mixtral처럼 전체 파라미터는 크지만 추론 시에는 일부 전문가 네트워크만 활성화하여 효율성 확보

## 참고 자료

### 핵심 논문
- [Attention Is All You Need (Vaswani et al., 2017)](https://arxiv.org/abs/1706.03762) - Transformer 아키텍처 원 논문
- [Training language models to follow instructions with human feedback (InstructGPT)](https://arxiv.org/abs/2203.02155) - RLHF 논문
- [Training Compute-Optimal Large Language Models (Chinchilla, 2022)](https://arxiv.org/abs/2203.15556) - Scaling Law 논문
- [Emergent Abilities of Large Language Models (Wei et al., 2022)](https://arxiv.org/abs/2206.07682) - 창발적 능력 정의
- [Hallucination is Inevitable (Xu et al., 2024)](https://arxiv.org/abs/2401.11817) - 할루시네이션의 이론적 불가피성
- [Why Language Models Hallucinate (OpenAI, 2025)](https://openai.com/index/why-language-models-hallucinate/) - 할루시네이션 원인 분석
- [Emergent Abilities in LLMs: A Survey (2025)](https://arxiv.org/abs/2503.05788) - 창발적 능력 종합 서베이

### 가이드 및 문서
- [The Illustrated Transformer (Jay Alammar)](https://jalammar.github.io/illustrated-transformer/) - Transformer 시각화 설명
- [Prompt Engineering Guide](https://www.promptingguide.ai/) - 프롬프트 엔지니어링 기법 총정리
- [Hugging Face NLP Course - BPE Tokenization](https://huggingface.co/learn/llm-course/en/chapter6/5) - BPE 토큰화 설명
- [IBM - What is RAG?](https://www.ibm.com/think/topics/retrieval-augmented-generation) - RAG 개념 설명
- [New LLM Pre-training and Post-training Paradigms (Sebastian Raschka, 2024)](https://sebastianraschka.com/blog/2024/new-llm-pre-training-and-post-training.html) - 최신 학습 패러다임

### 모델별 공식 자료
- [OpenAI API Documentation](https://platform.openai.com/docs/) - GPT 모델 공식 문서
- [Anthropic Claude Documentation](https://docs.anthropic.com/) - Claude 모델 공식 문서
- [Meta Llama](https://llama.meta.com/) - Llama 오픈소스 모델
- [Google Gemini](https://deepmind.google/technologies/gemini/) - Gemini 모델
