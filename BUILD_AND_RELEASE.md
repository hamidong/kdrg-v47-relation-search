# Windows exe 빌드 & GitHub Release 배포 가이드

이 문서는 Replit에서 코드를 수정한 뒤, GitHub Actions가 Windows exe를
자동으로 빌드해서 GitHub Release에 올리기까지의 전체 순서를 설명합니다.
Git이나 GitHub Actions를 잘 몰라도 순서대로 따라 하면 됩니다.

버전 번호, exe 파일명, Release 제목은 모두 `version.py` 한 곳에서만
관리합니다. 새 버전을 낼 때는 `version.py`의 `APP_VERSION` 값만 바꾸면
나머지는 자동으로 맞춰집니다.

---

## 0. 최초 1회만 하는 일 (Actions workflow 파일 직접 추가 필요)

이미 저장소에 `.github/workflows/build-windows-release.yml` 파일이 있다면
이 단계는 건너뛰어도 됩니다.

Replit-GitHub 연동 토큰은 보안상 "workflow" 권한이 없어서, 에이전트가
`.github/workflows/` 안의 파일은 API로 직접 만들 수 없습니다. 그래서
workflow 내용은 저장소의 `ci/build-windows-release.workflow.yml`에
임시로 올려두었습니다. **최초 1회만** 아래 순서로 실제 위치로 옮겨주세요
(GitHub 웹 화면에서 하는 것이라 1분이면 됩니다):

1. GitHub 저장소 페이지에서 `ci/build-windows-release.workflow.yml` 파일을 엽니다.
2. 우측 상단 연필(✏) 아이콘 → **Edit this file**을 눌러 내용 전체를 복사합니다.
3. 저장소 페이지 상단 **Add file** → **Create new file** 클릭
4. 파일명 입력란에 `.github/workflows/build-windows-release.yml`을 입력합니다
   (슬래시를 입력하면 GitHub가 자동으로 폴더를 만듭니다).
5. 복사한 내용을 붙여넣고 **Commit changes**를 클릭해 `main` 브랜치에 바로 커밋합니다.
6. (선택) 이제 필요 없어진 `ci/build-windows-release.workflow.yml`은 삭제해도 됩니다.

이 작업은 저장소당 최초 1회만 하면 됩니다. 이후 버전업 때는 이 단계를
반복할 필요가 없습니다.

---

## 1. Replit에서 GitHub로 변경사항 올리기

1. Replit 채팅에서 에이전트에게 "GitHub에 반영해줘"라고 요청하거나,
   좌측 Git 패널에서 변경 내용을 커밋 후 Push 합니다.
2. `main` 브랜치에 코드가 정상적으로 올라갔는지 GitHub 저장소 페이지에서
   확인합니다.

> 이 단계에서는 아직 exe가 빌드되지 않습니다. 태그를 만들어야 빌드가
> 시작됩니다 (2단계).

---

## 2. 태그 생성 (여기서부터 exe 빌드가 자동 시작됩니다)

`version.py`의 `APP_VERSION`이 예를 들어 `0.1.0`이면, 태그는 `v0.1.0`
입니다.

GitHub 저장소 웹페이지에서:

1. 저장소 페이지 오른쪽의 **Releases** → **Draft a new release** 클릭
2. **Choose a tag** → `v0.1.0`처럼 입력하고 **Create new tag: v0.1.0 on
   publish** 선택
3. Release 제목/설명은 비워둬도 됩니다 (Actions가 exe를 자동으로 붙여줍니다)
4. **Publish release** 클릭

또는 터미널에 익숙하면:

```bash
git tag v0.1.0
git push origin v0.1.0
```

태그(`v*.*.*` 형식)가 push되는 순간 GitHub Actions가 자동으로 시작됩니다.

---

## 3. GitHub Actions 진행 확인

1. GitHub 저장소 페이지 상단의 **Actions** 탭 클릭
2. `Build Windows exe and publish Release` workflow가 실행 중인지 확인
3. 아래 단계를 순서대로 진행합니다 (실패하면 다음 단계로 넘어가지 않습니다):
   - fixture validator 실행
   - GUI smoke test 실행 (offscreen)
   - 문법 검증 (py_compile)
   - PyInstaller 빌드
   - 배포 전 정적 검증 (exe 포함)
   - GitHub Release 생성 및 exe 업로드
4. 모든 단계가 초록색 체크로 끝나면 완료입니다. 보통 5~10분 정도 걸립니다.

실패하면 실패한 단계를 클릭해서 로그를 확인하세요. 대부분 아래 항목 중
하나입니다:
- fixture validator 실패 → 데이터에 문제가 있습니다.
- GUI smoke test 실패 → 코드 변경으로 기본 동작이 깨졌습니다.
- PyInstaller 빌드 실패 → 의존성 누락(주로 PySide6 관련) 문제입니다.

---

## 4. GitHub Release Assets 확인

1. 저장소 페이지의 **Releases** 탭으로 이동
2. 방금 만든 태그(예: `v0.1.0`)의 Release를 클릭
3. **Assets** 목록에 `KDRG_V47_Relation_Search_0.1.0.exe` 파일이 있는지
   확인합니다 (Actions artifact가 아니라 Release Assets에 올라갑니다).
4. 파일을 클릭해서 다운로드합니다.

---

## 5. Windows PC에서 exe 다운로드 후 테스트

exe를 받은 뒤, 실제 Windows PC에서 다음을 확인하세요.

- [ ] 설치 없이 더블클릭만으로 실행되는지
- [ ] 실행할 때 콘솔(까만 창)이 같이 뜨지 않는지
- [ ] 화면의 한글이 깨지지 않는지 (맑은 고딕이 정상적으로 보이는지)
- [ ] 창 크기와 배치가 기준 화면(1700x960 미리보기)과 비슷한지
- [ ] 처음 열었을 때 E011이 기본으로 선택되어 있는지
- [ ] 검색창에 코드(예: `E0110`)를 입력하면 결과가 나오는지
- [ ] "복수 코드 관계검색 펼치기" 버튼을 누르면 검색1/검색2 입력창이 나오는지
- [ ] 검색1에 `O1311`, 검색2에 `O1326`, 조건 관계를 `AND`로 놓고 검색하면
      E011에 "서로 다른 OR 조건식에 분산"이 표시되는지
- [ ] 코드표(TABLE) 펼치기 버튼과 뒤로가기가 정상 동작하는지
- [ ] 창을 닫을 때 오류창이 뜨지 않는지

문제가 있으면 어떤 단계에서 어떤 화면이 나왔는지 알려주시면 원인을 찾기
쉽습니다.

---

## 로컬(Windows PC)에서 직접 빌드하고 싶을 때

GitHub Actions 없이 로컬에서도 동일한 절차로 exe를 만들 수 있습니다.

```bat
build_windows.bat
```

개발 중 GUI를 바로 실행해보고 싶다면:

```bat
run_local.bat
```

---

## 새 버전 배포하기

1. `version.py`의 `APP_VERSION`을 올립니다 (예: `0.1.0` → `0.1.1`)
2. Replit에서 GitHub로 반영(push)
3. 새 버전에 맞는 태그를 만들어 push (`v0.1.1`)
4. 3~4단계를 그대로 반복

기존 Release를 덮어쓰지 않고 태그마다 새 Release가 생성됩니다.
