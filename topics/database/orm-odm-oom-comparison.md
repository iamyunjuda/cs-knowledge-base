# ORM vs ODM vs OOM — 객체 매핑 기술의 차이

## 핵심 정리

### 한 줄 요약

셋 다 **"객체(Object)와 저장소 사이의 변환을 자동화"**하는 기술이지만, **어떤 저장소와 매핑하느냐**가 다르다.

---

### 세 가지 매핑 기술 비교

```
┌─────────────────────────────────────────────────────────────┐
│                    Java/Kotlin 객체                           │
│                                                              │
│  public class User {                                         │
│      private Long id;                                        │
│      private String name;                                    │
│      private String email;                                   │
│  }                                                           │
└───────┬──────────────────┬──────────────────┬────────────────┘
        │                  │                  │
        │ ORM              │ ODM              │ OOM
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ RDB (관계형)  │  │ Document DB  │  │ 기타 저장소            │
│              │  │              │  │                      │
│ ┌──────────┐ │  │ {            │  │ - Object Storage     │
│ │ users    │ │  │   "_id": ... │  │ - Graph DB           │
│ │──────────│ │  │   "name": ...│  │ - Key-Value Store    │
│ │ id       │ │  │   "email":...│  │ - XML                │
│ │ name     │ │  │ }            │  │                      │
│ │ email    │ │  │              │  │                      │
│ └──────────┘ │  │ MongoDB      │  │                      │
│ MySQL        │  │ CouchDB      │  │                      │
│ PostgreSQL   │  │              │  │                      │
│ Oracle       │  │              │  │                      │
└──────────────┘  └──────────────┘  └──────────────────────┘
```

| | ORM | ODM | OOM |
|---|---|---|---|
| **풀네임** | Object-Relational Mapping | Object-Document Mapping | Object-Object Mapping |
| **매핑 대상** | 관계형 DB 테이블 | Document DB (JSON/BSON) | 객체 ↔ 객체 |
| **대표 기술** | JPA/Hibernate, MyBatis | Mongoose (Node.js), Spring Data MongoDB | MapStruct, ModelMapper |
| **핵심 문제** | 객체 ↔ 테이블 간 패러다임 불일치 | 객체 ↔ 문서 구조 변환 | DTO ↔ Entity 변환 |

---

### ORM (Object-Relational Mapping)

**객체와 관계형 DB 테이블 사이의 매핑.**

```
★ 가장 유명하고 가장 많이 쓰이는 매핑 기술

Java 객체                         RDB 테이블
┌──────────────┐                 ┌────────────────────┐
│ User         │     ORM         │ users              │
│  id: Long    │ ◄════════════►  │ id BIGINT PK       │
│  name: String│                 │ name VARCHAR(100)  │
│  orders: List│                 │                    │
└──────────────┘                 └────────────────────┘
       │                                │
       │ 1:N 관계                       │ FK: user_id
       ▼                                ▼
┌──────────────┐                 ┌────────────────────┐
│ Order        │     ORM         │ orders             │
│  id: Long    │ ◄════════════►  │ id BIGINT PK       │
│  amount: int │                 │ amount INT         │
│  user: User  │                 │ user_id BIGINT FK  │
└──────────────┘                 └────────────────────┘
```

```java
// JPA (Java 표준 ORM) 예시
@Entity
@Table(name = "users")
public class User {
    @Id @GeneratedValue
    private Long id;

    private String name;

    @OneToMany(mappedBy = "user")
    private List<Order> orders;
}

// 개발자는 SQL을 안 쓰고 객체로 조작
User user = entityManager.find(User.class, 1L);  // SELECT * FROM users WHERE id = 1
user.setName("새이름");
// → UPDATE users SET name = '새이름' WHERE id = 1  (자동 생성)
```

**ORM이 해결하는 "패러다임 불일치"**:

```
객체 세계                    관계형 세계
─────────                   ──────────
상속 (User extends Person)   → 테이블에는 상속 없음 (어떻게?)
참조 (user.getOrders())      → JOIN으로 해결
캡슐화 (private 필드)        → 컬럼은 다 public
그래프 탐색 (user.team.dept) → 여러 번 JOIN
동일성 (==, equals)          → PK 비교
```

**대표 기술**: JPA/Hibernate (Java), Django ORM (Python), ActiveRecord (Ruby), TypeORM (Node.js)

---

### ODM (Object-Document Mapping)

**객체와 Document DB(MongoDB 등)의 문서 사이의 매핑.**

```
Java/JS 객체                      MongoDB 문서 (BSON)
┌──────────────────┐              ┌─────────────────────────┐
│ User             │    ODM       │ {                       │
│  id: String      │ ◄════════►   │   "_id": ObjectId(...), │
│  name: String    │              │   "name": "홍길동",      │
│  address: Address│              │   "address": {          │
│  orders: List    │              │     "city": "서울",      │
│                  │              │     "zip": "12345"       │
└──────────────────┘              │   },                    │
                                  │   "orders": [           │
                                  │     { "amount": 50000 } │
                                  │   ]                     │
                                  │ }                       │
                                  └─────────────────────────┘
```

```java
// Spring Data MongoDB 예시 (Java ODM)
@Document(collection = "users")
public class User {
    @Id
    private String id;

    private String name;

    private Address address;      // 내장 문서 (embedded)

    private List<Order> orders;   // 배열로 저장
}

// RDB와 다른 점: JOIN 없이 하나의 문서에 다 들어감
User user = mongoTemplate.findById("abc123", User.class);
// → db.users.findOne({ _id: "abc123" })
```

**ORM과의 핵심 차이**:

```
ORM (관계형):
  - User와 Order가 별도 테이블 → JOIN 필요
  - 정규화된 구조 (중복 최소화)
  - 스키마 고정 (ALTER TABLE)

ODM (문서형):
  - User 안에 Order를 내장(embed) 가능 → JOIN 불필요
  - 비정규화 구조 (읽기 성능 우선)
  - 스키마 유연 (필드 자유롭게 추가)
```

**대표 기술**: Mongoose (Node.js + MongoDB), Spring Data MongoDB (Java), MongoEngine (Python)

---

### OOM (Object-Object Mapping)

**객체와 객체 사이의 변환. DB와 전혀 상관없다!**

```
Entity 객체                          DTO 객체
┌──────────────────┐                ┌──────────────────┐
│ User (Entity)    │     OOM        │ UserResponse     │
│  id: Long        │ ═══════════►   │  id: Long        │
│  name: String    │                │  name: String    │
│  password: String│  (password     │  orderCount: int │
│  email: String   │   제외!)       │                  │
│  orders: List    │                │  (orders를 count │
│  createdAt: ...  │                │   로 변환)        │
└──────────────────┘                └──────────────────┘
```

```java
// MapStruct 예시 (컴파일 타임 코드 생성)
@Mapper
public interface UserMapper {
    @Mapping(target = "orderCount", expression = "java(user.getOrders().size())")
    UserResponse toResponse(User user);
}

// 사용
UserResponse dto = userMapper.toResponse(userEntity);

// ModelMapper 예시 (런타임 리플렉션)
ModelMapper mapper = new ModelMapper();
UserResponse dto = mapper.map(userEntity, UserResponse.class);
```

**왜 필요한가?**

```
Controller에서 Entity를 직접 반환하면 안 되는 이유:
  ① 비밀번호 같은 민감 정보 노출
  ② Lazy Loading 프록시 직렬화 문제
  ③ 순환 참조 (User → Order → User → ...)
  ④ API 스펙과 DB 스키마가 강결합

→ Entity ↔ DTO 변환이 필수
→ 수동으로 하면 보일러플레이트 코드 폭발
→ OOM 라이브러리가 자동 변환
```

**대표 기술**: MapStruct (Java, 컴파일 타임), ModelMapper (Java, 런타임), AutoMapper (C#)

---

### 한눈에 비교

| | ORM | ODM | OOM |
|---|---|---|---|
| **매핑** | 객체 ↔ RDB 테이블 | 객체 ↔ Document(JSON) | 객체 ↔ 객체 |
| **목적** | SQL 자동 생성, 패러다임 불일치 해결 | 문서 CRUD 추상화 | DTO 변환 자동화 |
| **DB 의존** | ✅ (MySQL, PostgreSQL 등) | ✅ (MongoDB, CouchDB 등) | ❌ (DB 무관) |
| **Java 대표** | JPA/Hibernate | Spring Data MongoDB | MapStruct |
| **Node.js 대표** | TypeORM/Sequelize | Mongoose | class-transformer |
| **복잡도** | 높음 (N+1, 캐시, 지연로딩) | 중간 (인덱싱, 집계) | 낮음 (단순 변환) |

## 헷갈렸던 포인트

### Q1. MyBatis는 ORM인가?

**엄밀히는 아니다.** MyBatis는 **SQL Mapper**로 분류하는 게 더 정확하다:

```
ORM (JPA/Hibernate):
  → 객체를 주면 SQL을 자동 생성
  → 개발자가 SQL을 거의 안 씀
  → "객체 중심" 사고

SQL Mapper (MyBatis):
  → 개발자가 SQL을 직접 작성
  → SQL 결과를 객체에 매핑만 해줌
  → "SQL 중심" 사고
```

하지만 실무에서는 MyBatis도 ORM이라 부르는 경우가 흔하다. 넓은 의미로는 ORM에 포함.

### Q2. Spring Data JPA와 Spring Data MongoDB의 코드가 비슷한 이유는?

**Spring Data가 추상화 레이어**를 제공하기 때문:

```java
// Spring Data JPA (ORM)
public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findByName(String name);
}

// Spring Data MongoDB (ODM)
public interface UserRepository extends MongoRepository<User, String> {
    List<User> findByName(String name);
}

// 인터페이스가 거의 동일! → Spring Data의 Repository 추상화 덕분
// 내부 구현만 다름: JPA는 SQL, MongoDB는 BSON 쿼리
```

### Q3. OOM(MapStruct) 없이 수동으로 하면 안 되나?

된다. 필드 몇 개면 수동이 더 낫다:

```java
// 필드 3개 → 수동이 깔끔
public static UserResponse from(User user) {
    return new UserResponse(user.getId(), user.getName(), user.getEmail());
}

// 필드 20개 + 중첩 객체 → MapStruct가 편함
// 특히 Entity가 자주 바뀌는 경우 매핑 누락을 컴파일 타임에 잡아줌
```

## 참고 자료

- [JPA 공식 스펙 — Jakarta Persistence](https://jakarta.ee/specifications/persistence/)
- [Mongoose 공식 문서](https://mongoosejs.com/docs/guide.html)
- [MapStruct 공식 문서](https://mapstruct.org/documentation/stable/reference/html/)
- [Spring Data 공식 문서](https://spring.io/projects/spring-data)
