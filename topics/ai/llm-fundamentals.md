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
- 최근에는 RLHF 외에 DPO(Direct Preference Optimization) 등 더 효율적인 방법도 연구 중

### 추론 시 주요 파라미터

| 파라미터 | 설명 | 일반적인 범위 |
|---------|------|-------------|
| **Temperature** | 확률 분포의 날카로움을 조절. 낮을수록 결정적(greedy), 높을수록 다양한 출력 | 0.0 ~ 2.0 |
| **Top-p (Nucleus Sampling)** | 누적 확률이 p 이상인 토큰 집합에서만 샘플링 | 0.0 ~ 1.0 |
| **Top-k** | 확률 상위 k개 토큰에서만 샘플링 | 1 ~ 100+ |
| **Max Tokens** | 생성할 최대 토큰 수 | 모델마다 다름 |
| **Context Window** | 모델이 한 번에 처리할 수 있는 최대 토큰 수 (입력 + 출력) | 4K ~ 1M+ |

> Temperature 0은 항상 가장 확률 높은 토큰을 선택(deterministic). Temperature가 높으면 낮은 확률의 토큰도 선택될 수 있어 창의적이지만 일관성이 떨어짐.

### 주요 모델 비교 (2025년 기준)

| 모델 | 개발사 | 특징 |
|------|-------|------|
| **GPT-4o** | OpenAI | 멀티모달(텍스트/이미지/음성), 빠른 응답 |
| **Claude (Opus/Sonnet)** | Anthropic | 긴 컨텍스트(200K), 안전성 중시, 코딩 강점 |
| **Gemini** | Google | 멀티모달 네이티브, Google 서비스 통합 |
| **Llama 3** | Meta | 오픈소스, 상업적 사용 가능, 커뮤니티 활발 |
| **Mistral** | Mistral AI | 오픈소스, 경량 모델 대비 높은 성능 |

### 실용적 고려사항

**RAG (Retrieval-Augmented Generation):**
- LLM의 지식 한계(학습 데이터 시점까지만 알고 있음)를 보완하는 기법
- 외부 데이터베이스에서 관련 문서를 검색 → 검색 결과를 프롬프트에 포함 → LLM이 이를 기반으로 답변 생성
- Hallucination 감소, 최신 정보 반영, 출처 제공 가능

**프롬프트 엔지니어링:**
- Zero-shot: 예시 없이 바로 지시
- Few-shot: 몇 가지 예시를 포함하여 원하는 형식/패턴 유도
- Chain-of-Thought (CoT): "단계별로 생각해보세요" 등의 지시로 추론 과정을 명시적으로 유도
- System Prompt: 모델의 역할, 제약조건, 출력 형식을 사전에 정의

## 헷갈렸던 포인트

### Q: LLM은 정말로 "이해"하는 건가? 기존 NLP와 뭐가 다른 건가?

기존 NLP(TF-IDF, Word2Vec, LSTM 등)는 특정 태스크(감정 분류, 번역 등)에 맞게 별도로 학습해야 했다. LLM은 사전 학습만으로 다양한 태스크를 수행할 수 있는 범용 모델이라는 점이 근본적으로 다르다.

"이해"에 대해서는 논란이 있다. LLM은 통계적 패턴 매칭을 극도로 잘 수행하는 것이지, 사람처럼 의미를 "이해"하는 것은 아니라는 관점(Chinese Room Argument)이 있는 반면, 충분히 큰 규모의 패턴 매칭이 실질적 이해와 구분할 수 없다는 관점도 있다. 중요한 것은 **실용적으로 유용한 출력을 생성할 수 있다는 사실**이다.

### Q: Hallucination(환각)은 왜 발생하는가?

LLM은 확률적으로 "그럴듯한" 다음 토큰을 예측하는 모델이다. 학습 데이터에 없거나 모호한 정보에 대해서도, 문맥상 자연스러운 텍스트를 생성하려는 경향이 있어 **사실이 아닌 내용을 마치 사실인 것처럼** 출력한다.

원인:
1. **학습 데이터의 편향/불완전**: 잘못된 정보가 학습 데이터에 포함되어 있으면 그대로 재현
2. **확률 기반 생성의 본질**: "가장 그럴듯한" 것과 "사실인" 것은 다름
3. **Knowledge Cutoff**: 학습 시점 이후의 정보는 모름. 그런데도 자연스럽게 답변하려 함
4. **Compression Artifact**: 수조 토큰의 지식을 유한한 파라미터에 압축하면서 발생하는 손실

해결 방향: RAG, 외부 도구 연동(Calculator, Search), Fine-tuning, Confidence Score 활용

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

- [Attention Is All You Need (Vaswani et al., 2017)](https://arxiv.org/abs/1706.03762) - Transformer 원본 논문
- [The Illustrated Transformer (Jay Alammar)](https://jalammar.github.io/illustrated-transformer/) - Transformer 시각화 설명
- [Training language models to follow instructions with human feedback (InstructGPT)](https://arxiv.org/abs/2203.02155) - RLHF 논문
- [Training Compute-Optimal Large Language Models (Chinchilla)](https://arxiv.org/abs/2203.15556) - Scaling Law 논문
- [Anthropic Claude Documentation](https://docs.anthropic.com/) - Claude 모델 공식 문서
- [OpenAI API Documentation](https://platform.openai.com/docs/) - GPT 모델 공식 문서
