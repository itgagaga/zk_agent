from crawler.crawl_job import _parse_job_cards, _parse_recruitment_events
from crawler import crawl_job


def test_parse_public_job_cards():
    html = """
    <div class="jobs-list">
      <a class="job-block card" href="job-detail?id=42">
        <div class="job-name">农艺师</div>
        <div class="job-time">07/18 发布</div>
        <div class="job-company">广州农业公司</div>
        <div class="job-salary">5000～8000元/月</div>
        <div class="job-edu">本科生</div>
        <div class="job-industry">农业</div>
        <div class="third-line">五险一金,双休</div>
      </a>
    </div>
    """

    result = _parse_job_cards(html, "https://job.example/web/index/job-list")

    assert result == [
        {
            "id": "42",
            "name": "农艺师",
            "published": "07/18 发布",
            "company": "广州农业公司",
            "salary": "5000～8000元/月",
            "education": "本科生",
            "industry": "农业",
            "location": "",
            "benefits": "五险一金,双休",
            "url": "https://job.example/web/index/job-detail?id=42",
            "source_url": "https://job.example/web/index/job-list",
            "status": "discovered",
            "error": "",
        }
    ]


def test_parse_recruitment_events():
    html = """
    <a class="preach-block" href="preach-detail?id=7">
      <div class="preach-name">校园宣讲会</div>
      <div class="preach-time">2026/07/18 14:00 - 16:00</div>
      <div class="preach-company">广州农业公司</div>
      <div class="preach-address">白云校区杨楼204</div>
    </a>
    """

    result = _parse_recruitment_events(
        html, "https://job.example/web/index/preach-list"
    )

    assert result[0]["id"] == "7"
    assert result[0]["name"] == "校园宣讲会"
    assert result[0]["company"] == "广州农业公司"
    assert result[0]["url"].endswith("preach-detail?id=7")


def test_write_job_detail_metadata_uses_detail_url(monkeypatch):
    saved = []
    monkeypatch.setattr(
        crawl_job,
        "save_metadata",
        lambda subdir, filename, data: saved.append((subdir, filename, data)),
    )

    count = crawl_job.write_detail_metadata(
        [
            {
                "id": "42",
                "name": "农艺师",
                "company": "广州农业公司",
                "published": "07/18 发布",
                "url": "https://job.example/job-detail?id=42",
                "source_url": "https://job.example/job-list",
                "status": "downloaded",
            },
            {
                "id": "43",
                "name": "失败职位",
                "url": "https://job.example/job-detail?id=43",
                "status": "detail_failed",
            },
        ],
        "job",
    )

    assert count == 1
    assert saved[0][0:2] == ("job", "job_42.json")
    assert saved[0][2]["title"] == "农艺师"
    assert saved[0][2]["source_url"] == "https://job.example/job-detail?id=42"
    assert saved[0][2]["document_type"] == "职位详情"


def test_write_event_detail_metadata_uses_event_stem(monkeypatch):
    saved = []
    monkeypatch.setattr(
        crawl_job,
        "save_metadata",
        lambda subdir, filename, data: saved.append((filename, data)),
    )

    count = crawl_job.write_detail_metadata(
        [
            {
                "id": "7",
                "name": "校园宣讲会",
                "company": "广州农业公司",
                "time": "2026/07/18 14:00 - 16:00",
                "url": "https://job.example/preach-detail?id=7",
                "status": "downloaded",
            }
        ],
        "event",
    )

    assert count == 1
    assert saved[0][0] == "event_7.json"
    assert saved[0][1]["subcategory"] == "校园招聘活动"
    assert saved[0][1]["document_type"] == "招聘活动"
