# 정책 파일 관리 가이드라인

- 각 정책 파일은 JSON 배열로 작성하며, 주석은 포함하지 않는다.
- 정책 설명, 예시, 관리 규칙 등은 이 README.md에 문서화한다.
- 예시:
  ```json
  [
    {"xpath": "/EXPERIMENT/TITLE", "type": "warn", "note": "제목 변경 경고"},
    {"xpath": "/EXPERIMENT/IDENTIFIERS/PRIMARY_ID", "type": "error", "note": "필수 식별자"}
  ]
  ```
- 정책 유형(type):
  - error: 반드시 일치해야 하는 필드(불일치 시 오류)
  - warn: 변경 시 경고(검토 필요)
  - allow: 변경 허용(무시 가능)
- 정책 파일은 각 XML 루트 태그명에 맞춰 별도 관리한다.
- 정책 추가/수정 시 반드시 JSON 문법을 준수한다.
- 정책별 상세 설명은 note 필드에 작성한다. 