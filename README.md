# yeonsu-tools — Claude Code 플러그인 마켓플레이스

개인용 Claude Code 플러그인 모음. 현재 `stock-analyst` 하나 포함.

## 구조

```
stock-analyst-marketplace/
├── .claude-plugin/
│   └── marketplace.json          # 마켓플레이스 카탈로그
└── plugins/
    └── stock-analyst/
        ├── .claude-plugin/
        │   └── plugin.json       # 플러그인 매니페스트
        ├── commands/
        │   └── analyze.md        # /stock-analyst:analyze 슬래시 명령
        ├── skills/
        │   └── stock-analyst/    # 스킬 본체 (SKILL.md + scripts + reference)
        └── README.md
```

## 설치 방법

### A. 로컬에서 바로 테스트 (가장 빠름)

이 폴더를 로컬에 둔 상태에서 Claude Code 안에서:

```
/plugin marketplace add ./stock-analyst-marketplace
/plugin install stock-analyst@yeonsu-tools
```

검증:
```
/plugin validate ./stock-analyst-marketplace
```

### B. Git 저장소로 배포 (다른 기기에서도 사용)

이 폴더를 GitHub/GitLab 저장소에 push 한 뒤:

```
# GitHub
/plugin marketplace add <owner>/<repo>

# 자체 GitLab 등 git URL
/plugin marketplace add https://gitlab.example.com/yeonsu/stock-analyst-marketplace.git

/plugin install stock-analyst@yeonsu-tools
```

> 사설 저장소면 git 자격증명(`gh auth login` 또는 credential helper)이 설정돼 있어야 한다.

## 설치 후

1. 파이썬 의존성 설치: `pip install -r plugins/stock-analyst/skills/stock-analyst/requirements.txt`
2. 인증정보 설정: `plugins/stock-analyst/README.md` 참고 (`~/.kis/credentials.yaml` 권장)
3. 대화로 사용: `삼성전자 분석해줘`

## 인증정보는 저장소에 넣지 말 것

`config/credentials.yaml` 은 `.gitignore` 로 제외돼 있다. App Key/Secret 을 커밋하지 말 것.
플러그인은 업데이트 시 덮어써지므로 인증정보는 `~/.kis/credentials.yaml` 또는 환경변수로 관리한다.
