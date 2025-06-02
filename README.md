# XMLmeta 파이프라인 설명

이 프로젝트는 KBDS의 메타데이터(XML)를 DDBJ 제출 규격에 맞는 XML로 변환하고, 공식 XSD로 검증 하는 파이프라인을 구축하는 것을 목표로 합니다.

## 파이프라인 디렉토리 및 주요 경로

- **BioProject**: `pipeline_bioproject/main.py`
- **BioSample**: `pipeline_biosample/main.py`
- **Experiment**: `pipeline_experiment/main.py`
- **Run**: `pipeline_run/main.py`
- **Submission**: `pipeline_submission/main.py`

---

## 인풋 파일 경로

- BioProject: `xml_submitted/ddbj_bioproject.xml`
- BioSample: `xml_submitted/ddbj_biosample.xml`
- Experiment: `xml_submitted/ddbj_bioExperiment.xml`
- Run: `xml_submitted/ddbj_run.xml`, `xml_submitted/ddbj_run_file_path.xml`
- Submission: `xml_submitted/ddbj_bioExperiment.xml`, `xml_submitted/ddbj_run.xml`

## 아웃풋 파일 경로

- 모든 파이프라인의 결과 XML: `xml_fixed/` 디렉토리 하위에 저장
  - 예시: `xml_fixed/ddbj_bioproject.fixed.xml`, `xml_fixed/ddbj_biosample.fixed.xml` 등

## XSD 검증용 파일 경로

- XSD 파일들은 별도 저장소에서 받아야 하며, 아래 경로에 위치해야 합니다.
  - BioProject: `pub/docs/bioproject/xsd/Package.xsd`
  - BioSample: `pub/docs/biosample/xsd/biosample_set.xsd`
  - Experiment: `pub/docs/dra/xsd/1-6/SRA.experiment.xsd`
  - Run: `pub/docs/dra/xsd/1-6/SRA.run.xsd`
  - Submission: `pub/docs/dra/xsd/1-6/SRA.submission.xsd`
- **XSD 파일들은 반드시 직접 git clone 또는 수동 복사로 준비해야 합니다.**

### XSD 파일 준비 방법 예시

1. [DDBJ 공식 XSD 저장소](https://github.com/ddbj/ddbj-xml-schemas)에서 필요한 파일을 clone 합니다.
2. 필요한 XSD 파일을 본 프로젝트의 지정된 경로(`pub/docs/...`)에 복사하거나, 심볼릭 링크를 생성합니다.
- **경로가 다를 경우, 각 파이프라인 코드의 XSD_PATH 상수를 수정해야 합니다.**
- 최신 XSD가 필요하다면 공식 저장소에서 주기적으로 업데이트하세요.
```bash
git clone https://github.com/ddbj/ddbj-xml-schemas.git
```
---

## 파이프라인별 주요 변환 로직 및 구조 변화

### 1. BioProject (`pipeline_bioproject/main.py`)
- **인풋:** `xml_submitted/ddbj_bioproject.xml`, `xml_submitted/ddbj_biosample.xml`, `xml_submitted/ddbj_run.xml`
- **주요 추출/변환:**
  - BioSample, Run XML에서 project별 taxID, OrganismName, 날짜 정보 등 보조 데이터 추출
  - 누락/오류 필드 자동 보정 (예: ArchiveID, Grant, ProjectType, SubmitterOrganization 등)
  - ProjectTypeSubmission 구조를 기본값(eOther 등)으로 생성, Organism 정보 보정
  - SubmitterOrganization, ProjectSubmissionDate 등 위치/포맷 보정
  - Submission 블록을 Package 하위에 별도 추가
- **구조 변화 예시:**
  - 입력 XML의 누락/불일치 필드 자동 채움 및 위치 이동
  - 보조 XML에서 Organism, 날짜 등 정보 병합
  - XSD 요구 구조에 맞게 필드명/위치/속성 보정

### 2. BioSample (`pipeline_biosample/main.py`)
- **인풋:** `xml_submitted/ddbj_biosample.xml`, `xml_submitted/ddbj_bioproject.xml`, `xml_submitted/ddbj_bioExperiment.xml`
- **주요 추출/변환:**
  - BioProject에서 owner 정보, BioExperiment에서 isolate/isolation_source 추출
  - SAMPLE_ATTRIBUTES의 태그명/값을 snake_case로 변환 및 표준화
  - 필수 속성(REQUIRED_ATTRIBUTES) 누락 시 'unknown' 등 기본값 채움
  - Description, Owner, Models, Attributes 등 XSD 요구 구조로 재구성
  - <SAMPLE_SET> → <BioSampleSet>, <SAMPLE> → <BioSample> 등 태그명 변경
- **구조 변화 예시:**
  - 속성명 camelCase → snake_case 변환
  - 필수 필드 누락 시 기본값 보정
  - Owner, Description, Models 등 XSD 구조에 맞게 재배치

### 3. Experiment (`pipeline_experiment/main.py`)
- **인풋:** `xml_submitted/ddbj_bioExperiment.xml`
- **주요 추출/변환:**
  - 불필요한 속성(refcenter, refname 등) 제거
  - IDENTIFIERS 내 PRIMARY_ID, SUBMITTER_ID 등 보정 및 값 채움
  - DESIGN 하위 구조(설명, 샘플, 라이브러리 등) 순서 및 필수 필드 보정
  - LIBRARY_SELECTION, LIBRARY_STRATEGY, LIBRARY_SOURCE 등 허용값만 남기고 나머지는 'other'/'OTHER'로 보정
  - INSTRUMENT_MODEL 허용값 외 'unspecified'로 보정
- **구조 변화 예시:**
  - DESIGN, LIBRARY_DESCRIPTOR 등 하위 구조 순서/필수값 보정
  - 허용값 외 값은 'other'/'unspecified'로 변환

### 4. Run (`pipeline_run/main.py`)
- **인풋:** `xml_submitted/ddbj_run.xml`, `xml_submitted/ddbj_run_file_path.xml`
- **주요 추출/변환:**
  - ddbj_run_file_path.xml에서 파일 정보(DATA_BLOCK) 추출 및 병합
  - RUN/EXPERIMENT_REF의 IDENTIFIERS에서 PRIMARY_ID 제거, UUID 필드 추가
  - RUN TITLE에 accession 추가, 파일 정보에 checksum_method 등 기본값 추가
  - 빈 값/None/빈 리스트/빈 dict 제거
- **구조 변화 예시:**
  - DATA_BLOCK, FILES 등 파일 정보 병합
  - IDENTIFIERS 구조 보정 (UUID 필드화)
  - TITLE, FILES 등 필드 보정 및 기본값 추가

### 5. Submission (`pipeline_submission/main.py`)
- **인풋:** `xml_submitted/ddbj_bioExperiment.xml`, `xml_submitted/ddbj_run.xml`
- **주요 추출/변환:**
  - EXPERIMENT, RUN에서 accession 등 주요 ID 추출
  - SUBMISSION XML 구조 생성 (IDENTIFIERS, CONTACTS, ACTIONS 등)
  - DSUB ID 등 소스가 없는 값은 빈 값으로 처리
  - 각 run별로 별도 submission XML 생성
- **구조 변화 예시:**
  - 입력 정보 기반으로 SUBMISSION 구조 생성 및 필드 채움
  - 여러 run에 대해 반복적으로 아웃풋 생성

---

## 파이프라인별 사용법

### 1. BioProject
```bash
python pipeline_bioproject/main.py
```
- 입력: `xml_submitted/ddbj_bioproject.xml`
- 출력: `xml_fixed/ddbj_bioproject.fixed.xml`
- XSD 검증: `pub/docs/bioproject/xsd/Package.xsd`

### 2. BioSample
```bash
python pipeline_biosample/main.py
```
- 입력: `xml_submitted/ddbj_biosample.xml`
- 출력: `xml_fixed/ddbj_biosample.fixed.xml`
- XSD 검증: `pub/docs/biosample/xsd/biosample_set.xsd`

### 3. Experiment
```bash
python pipeline_experiment/main.py
```
- 입력: `xml_submitted/ddbj_bioExperiment.xml`
- 출력: `xml_fixed/ddbj_bioExperiment.fixed.xml`
- XSD 검증: `pub/docs/dra/xsd/1-6/SRA.experiment.xsd`

### 4. Run
```bash
python pipeline_run/main.py
```
- 입력: `xml_submitted/ddbj_run.xml`, `xml_submitted/ddbj_run_file_path.xml`
- 출력: `xml_fixed/ddbj_run.fixed.xml`
- XSD 검증: `pub/docs/dra/xsd/1-6/SRA.run.xsd`

### 5. Submission
```bash
python pipeline_submission/main.py <run_id>  # 특정 run만
python pipeline_submission/main.py --all     # 전체 run 일괄
```
- 입력: `xml_submitted/ddbj_bioExperiment.xml`, `xml_submitted/ddbj_run.xml`
- 출력: `xml_fixed/ddbj_submission_<exp_id>_<run_id>.fixed.xml`
- XSD 검증: `pub/docs/dra/xsd/1-6/SRA.submission.xsd`

---

## 참고
- 각 파이프라인 실행 시, 변환 후 XSD 검증 결과가 터미널에 바로 출력됩니다.
- 모든 결과 XML은 `xml_fixed/` 하위에 저장됩니다.
- XSD 파일이 없으면 검증이 동작하지 않으니 반드시 준비하세요.
