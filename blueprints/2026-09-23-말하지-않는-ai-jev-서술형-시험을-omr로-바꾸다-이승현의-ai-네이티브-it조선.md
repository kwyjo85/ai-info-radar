#서술형 시험 자동 채점 AI 'Jev' 벤치마킹 — 개인용 자동 채점·피드백 파이프라인 구축

## 개요
Jev는 서술형 답안을 채점 기준에 따라 자동으로 정오 판정하는 AI로, 사람이 손으로 채점하던 서술형 시험을 사실상 OMR 수준으로 자동화한 사례다. 개인 MacBook 환경에서는 Claude Code + Claude API(비전+텍스트)를 활용해 이미지/PDF로 스캔된 서술형 답안지를 채점 기준(rubric) 매칭 방식으로 자동 채점하고, 채점 대행 서비스(과외·학원·온라인 강사 대상)로 수익화할 수 있다. 기존 OCR+규칙기반 채점보다 자연어 이해가 필요한 서술형에 강점이 있어 틈새 B2B 수요가 있다.

## 구현 가능성 — 중
- 근거(가능): Claude의 비전 입력으로 손글씨/스캔 답안 OCR 및 이해가 가능하고, rubric을 프롬프트로 구조화하면 채점 근거를 함께 출력시킬 수 있음. Claude Code로 배치 처리 스크립트 작성이 용이함.
- 근거(제약): 손글씨 인식 정확도, 채점 기준의 모호성(부분점수 판단), 실제 교육기관 대상 신뢰성 검증(정확도 보증) 확보가 필요해 단순 MVP 이상은 '중' 난이도로 판단.

## 필요 도구
- Claude API (Sonnet/Opus, 비전 지원) — 유료, 종량제 (claude-api 스킬 참고해 최신 가격 확인)
- Claude Code — 로컬 자동화 스크립트/배치 파이프라인 개발용, 무료(구독 포함)
- pdf2image 또는 PyMuPDF (fitz) — 무료, PDF→이미지 변환
- Pillow — 무료, 이미지 전처리(크롭/이진화)
- pandas — 무료, 채점 결과 집계/리포트
- Google Sheets API 또는 Notion API — 무료(개인 사용량), 채점 결과 대시보드 공유
- (선택) Tesseract OCR — 무료, 보조 텍스트 추출용 백업
- (선택) Stripe API — 유료(수수료 기반), 채점 대행 서비스 결제 연동 시

## 구현 단계
1. Claude Code로 `scripts/exam_grader/` 프로젝트 생성, 입력(스캔 PDF/이미지) → 출력(채점표 CSV/JSON) 파이프라인 구조 설계.
2. 샘플 서술형 시험지(교사가 만든 문제+모범답안+채점기준표) 5~10건을 텍스트로 확보해 rubric 스키마(문항ID, 배점, 핵심 키워드/논리 요소, 감점 조건) 정의.
3. PDF/이미지 답안지를 pdf2image로 문항 단위 크롭 → Claude 비전 API에 (모범답안+rubric+학생답안 이미지)를 함께 전달해 "점수, 근거, 부족한 부분"을 JSON으로 반환받는 프롬프트 작성 및 테스트.
4. 채점 결과 100건 이상을 실제 교사 채점과 비교해 정확도(±1점 이내 일치율) 측정, 오차 큰 문항 유형 파악 후 rubric 프롬프트 보정.
5. Claude Code로 배치 실행 스크립트 작성(폴더 감시 → 자동 채점 → CSV/Sheets 업로드), 채점 근거를 포함한 PDF 리포트 자동 생성 기능 추가.
6. 학원/과외 강사 대상 파일럿 진행: 무료 체험 5건 제공 → 정확도/시간 절감 효과 제시 → 건당/월 구독 요금제 설계.
7. 결제(Stripe) 및 간단한 웹 업로드 폼(또는 이메일 접수) 연동해 서비스화, 수요 검증 후 확장 여부 결정.

## 예상 공수
- MVP(1~4단계): 약 20~30시간, 난이도 중
- 서비스화(5~7단계): 추가 30~40시간, 난이도 중상(정확도 검증·영업 활동 포함)

## 리스크/유의점
- 채점 오류로 인한 신뢰 손상 리스크: 초기에는 "AI 초안 채점 + 사람 최종 확인" 하이브리드로 포지셔닝해야 함.
- 학생 개인정보(답안지) 처리 시 교육기관의 개인정보보호 동의 절차 필요.
- Jev와 직접 경쟁하는 상용 서비스가 이미 존재할 경우, 개인 프로젝트는 니치(특정 과목/소규모 학원) 타겟으로 차별화 필요.
- Claude API 비용이 답안 이미지 수에 비례해 증가하므로 문항 단위 배치 최적화(캐싱, 저해상도 우선 처리)로 원가 관리 필요.

---
원본: https://news.google.com/rss/articles/CBMidEFVX3lxTE5rT0NzVEp6SFlzVGNEcWdCSXhRSng0MnRyZVhobjl3ZTJfa2ZrTUlNaU9ULVJuWGJhRV9RVE1hdXlrVDlRczlxLWNOdlZHaEllNXJvMkNUQ3ZOemt0ZmRQZ3NDMkROU2ZhRlUySW1rMzZXNnVH0gF0QVVfeXFMTmtPQ3NUSnpIWXNUY0RxZ0JJeFFKeDQydHJlWGhuOXdlMl9rZmtNSU1pT1QtUm5YYmFFX1FUTWF1eWtUOVFzOXEtY052VkdoSWU1cm8yQ1RDdk56a3RmZFBnc0MyRE5TZmFGVTJJbWszNlc2dUc?oc=5
